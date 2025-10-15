# Basic Strategy - Resource optimization for non-HPA deployments with fixed replica counts
# 
# This strategy is designed for workloads without HPA (Horizontal Pod Autoscaler) where
# the number of replicas is fixed and doesn't auto-scale.
#
# Algorithm:
# - Calculates CPU/Memory requests based on configurable percentiles (default 90th)
# - Sets limits as a percentage of the request for CPU and as a percentage of peak for Memory
# - Uses total resource usage across all pods (already summed by Prometheus grouping)

import textwrap

import numpy as np
import pydantic as pd

from robusta_krr.api.models import K8sObjectData, MetricsPodData, PodsTimeData, ResourceRecommendation, ResourceType, RunResult
from robusta_krr.api.strategies import BaseStrategy, StrategySettings
from robusta_krr.core.models.objects import K8sObjectData

from robusta_krr.core.integrations.prometheus.metrics import (
  TotalCPULoader,
  TotalCPUAmountLoader,
  TotalMemoryLoader,
  TotalMemoryAmountLoader,
)

class BasicStrategySettings(StrategySettings):
    """Settings for the Basic strategy for non-HPA workloads."""

    cpu_request_percentile: float = pd.Field(
        90, gt=0, le=100,
        description="The percentile to use for the CPU request (default 90 = 90th percentile).",
    )
    cpu_limit_percent: float = pd.Field(
        150, gt=0,
        description="CPU limit as percentage of request (default 150 = limit is 1.5x request)"
    )
    mem_request_percentile: float = pd.Field(
        90, gt=0, le=100,
        description="The percentile to use for the Memory request (default 90 = 90th percentile).",
    )
    memory_limit_peak_percent: float = pd.Field(
        120, gt=0,
        description="Memory limit as percentage of peak usage (default 150 = limit is 1.5x peak usage)"
    )
    points_required: int = pd.Field(
        100, ge=1, 
        description="The number of data points required to make a recommendation for a resource."
    )
    # Note: This strategy is designed for non-HPA workloads

    def calculate_cpu_proposal(self, data: PodsTimeData) -> float:
        """
        Calculate the CPU proposal based on the configured percentile.
        
        For non-HPA workloads, we use the total usage percentile directly
        since the number of replicas is fixed.
        """
        if len(data) == 0:
            return float("NaN")

        # Get total usage (already summed by Prometheus grouping by container only)
        all_values = list(data.values())[0][:, 1]

        if len(all_values) == 0:
            return float("NaN")

        # Calculate the percentile of total usage
        percentile_value = np.percentile(all_values, self.cpu_request_percentile)

        return percentile_value

    def calculate_memory_proposal(self, data: PodsTimeData) -> tuple[float, float]:
        """
        Calculate the Memory proposal based on the configured percentile for request
        and peak usage for limit.
        
        Returns: (request, peak_value) tuple
        """
        if len(data) == 0:
            return (float("NaN"), float("NaN"))

        # Get total usage (already summed by Prometheus grouping by container only)
        all_values = list(data.values())[0][:, 1]

        if len(all_values) == 0:
            return (float("NaN"), float("NaN"))

        # Calculate the percentile for request
        percentile_value = np.percentile(all_values, self.mem_request_percentile)
        
        # Get peak value (max) for limit calculation
        peak_value = np.max(all_values)

        return (percentile_value, peak_value)




class BasicStrategy(BaseStrategy[BasicStrategySettings]):
    """
    Basic Strategy for resource optimization of non-HPA workloads.
    
    Designed for deployments with fixed replica counts (no HPA).
    Sets requests based on usage percentiles and limits as percentages.
    """

    display_name = "basic"
    rich_console = True

    @property
    def metrics(self):
        """Define the metrics needed for this strategy."""
        return [
            TotalCPULoader,  # Get total CPU usage across all pods
            TotalMemoryLoader,  # Get total memory usage across all pods
            TotalCPUAmountLoader,  # Get data point count for CPU
            TotalMemoryAmountLoader,  # Get data point count for memory
        ]

    @property
    def description(self):
        """Generate the strategy description for CLI help."""
        s = textwrap.dedent(f"""\
            Basic Strategy for Non-HPA Workloads
            
            CPU request: {self.settings.cpu_request_percentile}th percentile
            CPU limit: {self.settings.cpu_limit_percent}% of request
            Memory request: {self.settings.mem_request_percentile}th percentile
            Memory limit: {self.settings.memory_limit_peak_percent}% of peak usage
            History: {self.settings.history_duration} hours
            Step: {self.settings.timeframe_duration} minutes
            
            This strategy is designed for workloads with fixed replica counts (no HPA).
            It sets resource requests based on historical usage percentiles and applies
            configurable limit percentages for burst capacity.

            All parameters can be customized. For example:
            `krr basic --cpu_request_percentile=90 --cpu_limit_percent=150 --mem_request_percentile=90 --memory_limit_peak_percent=150`
            
            Note: This strategy is designed for non-HPA workloads.
            """)

        return s

    def __calculate_cpu_proposal(
        self, history_data: MetricsPodData, object_data: K8sObjectData
    ) -> ResourceRecommendation:
        """Calculate CPU request/limit recommendations."""
        data = history_data["TotalCPULoader"]  # Get total CPU usage across all pods

        if len(data) == 0:
            return ResourceRecommendation.undefined(info="No data")

        # Check if we have enough data points
        data_count = {pod: values[0, 1] for pod, values in history_data["TotalCPUAmountLoader"].items()}
        total_points_count = sum(data_count.values())

        if total_points_count < self.settings.points_required:
            return ResourceRecommendation.undefined(info="Not enough data")

        # Calculate the CPU proposal using configured percentile
        cpu_usage = self.settings.calculate_cpu_proposal(data)
        
        # Apply cpu_min_value to ensure limit percentage is calculated correctly
        from robusta_krr.core.models.config import settings as krr_settings
        cpu_min_cores = krr_settings.cpu_min_value / 1000  # Convert from millicores to cores
        cpu_usage = max(cpu_usage, cpu_min_cores)
        
        # Calculate limit as percentage of request
        cpu_limit = cpu_usage * (self.settings.cpu_limit_percent / 100)
        
        return ResourceRecommendation(request=cpu_usage, limit=cpu_limit)

    def __calculate_memory_proposal(
        self, history_data: MetricsPodData, object_data: K8sObjectData
    ) -> ResourceRecommendation:
        """Calculate memory request/limit recommendations."""
        data = history_data["TotalMemoryLoader"]  # Get total memory usage across all pods

        if len(data) == 0:
            return ResourceRecommendation.undefined(info="No data")

        # Check if we have enough data points
        data_count = {pod: values[0, 1] for pod, values in history_data["TotalMemoryAmountLoader"].items()}
        total_points_count = sum(data_count.values())

        if total_points_count < self.settings.points_required:
            return ResourceRecommendation.undefined(info="Not enough data")

        # Calculate the memory proposal (returns both request percentile and peak value)
        memory_usage, peak_usage = self.settings.calculate_memory_proposal(data)
        
        # Apply mem_min to ensure we meet minimum requirements
        from robusta_krr.core.models.config import settings as krr_settings
        memory_min_bytes = krr_settings.memory_min_value * (1024**2)  # Convert from MiB to bytes
        memory_usage = max(memory_usage, memory_min_bytes)
        
        # Calculate limit as percentage of peak usage (not request)
        memory_limit = peak_usage * (self.settings.memory_limit_peak_percent / 100)
        
        # Ensure limit is at least equal to request
        memory_limit = max(memory_limit, memory_usage)
        
        return ResourceRecommendation(request=memory_usage, limit=memory_limit)

    def run(self, history_data: MetricsPodData, object_data: K8sObjectData) -> RunResult:
        """Execute the strategy and return recommendations for both CPU and memory."""
        return {
            ResourceType.CPU: self.__calculate_cpu_proposal(history_data, object_data),
            ResourceType.Memory: self.__calculate_memory_proposal(history_data, object_data),
        }
