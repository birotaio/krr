# HPA Optimized Strategy - Cost optimization for HPA-enabled deployments with variable usage
# 
# This strategy is designed for clusters with HPA where you want to optimize costs
# by running with just 2 pods during low-traffic periods (40% of the time).
#
# Algorithm:
# - Calculates the 40th percentile of total resource usage across all pods
# - Divides by 2 (so 2 pods can handle the low-usage baseline)
# - Sets both request and limit equal for predictable resource allocation

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

class HPAStrategySettings(StrategySettings):
    """Settings for the HPA Optimized cost-saving strategy."""
    
    low_usage_percentile: float = pd.Field(
        40, gt=0, le=100, 
        description="The percentile representing low usage periods (default 40th = low usage 40% of the time)"
    )
    target_pod_count: int = pd.Field(
        2, ge=1, 
        description="Target number of pods to handle low-usage baseline (default 2)"
    )
    max_replicas: int | None = pd.Field(
        None, ge=1,
        description="Maximum number of replicas from HPA config. If set, validates that max replicas can handle peak load."
    )
    cpu_limit_percent: float = pd.Field(
        200, gt=0, 
        description="CPU limit as percentage of request (default 100 = limit equals request, 150 = limit is 1.5x request)"
    )
    memory_limit_percent: float = pd.Field(
        300, gt=0, 
        description="Memory limit as percentage of request (default 100 = limit equals request, 150 = limit is 1.5x request)"
    )
    points_required: int = pd.Field(
        100, ge=1, 
        description="The number of data points required to make a recommendation for a resource."
    )
    # Note: This strategy is designed for HPA workloads, so we always allow HPA
    # No allow_hpa flag to avoid CLI conflicts

    def calculate_resource_proposal(self, data: PodsTimeData, resource_name: str = "resource") -> float:
        """
        Calculate the resource proposal based on low usage percentile.
        
        1. Get total cluster usage (already summed by Prometheus grouping by container only)
        2. Calculate the specified percentile (default 40th)
        3. Divide by target pod count (default 2)
        4. If max_replicas is set, validate that max replicas can handle high load (90th percentile)
        
        This gives us the per-pod request needed so that target_pod_count pods
        can handle the low-usage baseline, while max_replicas can handle sustained high load.
        Burst/spikes are handled by the limit percentage.
        """
        if len(data) == 0:
            return float("NaN")

        # Since we're now grouping by container only, we get total usage directly
        # There should be only one key (the container name) in the data dict
        all_values = list(data.values())[0][:, 1]

        if len(all_values) == 0:
            return float("NaN")

        # Calculate the percentile of total usage
        percentile_value = np.percentile(all_values, self.low_usage_percentile)

        # Calculate statistics
        p90_value = np.percentile(all_values, 90)
        max_value = np.max(all_values)
        min_value = np.min(all_values)
        mean_value = np.mean(all_values)
        median_value = np.median(all_values)

        # Calculate baseline request (for low usage periods)
        per_pod_request = percentile_value / self.target_pod_count
        container_name = list(data.keys())[0]
        # Validate max replicas can handle sustained high load (90th percentile) if configured
        if self.max_replicas is not None:
            # Calculate what request would be needed if we scale to max replicas at 90th percentile
            # (True peak spikes above 90th will be handled by the limit percentage)
            request_for_high_load = p90_value / self.max_replicas
            
            # If the request needed for high load is higher, use that instead
            if request_for_high_load > per_pod_request:
                
                print(f"\n⚠️  WARNING: Max replicas validation for {container_name} ({resource_name})")
                print(f"  - Max: {max_value:.4f} 90th percentile usage: {p90_value:.4f} (sustained high load)")
                print(f"  - Original request (low usage): {per_pod_request:.4f} Request needed for 90th percentile: {request_for_high_load:.4f}")
                per_pod_request = request_for_high_load

        # Debug logging
        print(f"\n Processing container: {container_name} ({resource_name})")
        print(f"  - Total data points: {len(all_values)}")
        print(f"  - Min: {min_value:.4f}, Max: {max_value:.4f}")
        print(f"  - Mean: {mean_value:.4f}, Median: {median_value:.4f}")
        print(f"  - {self.low_usage_percentile}th percentile: {percentile_value:.4f}")
        print(f"  - Per-pod request (÷ {self.target_pod_count}): {per_pod_request:.4f}")

        return per_pod_request


class HPAStrategy(BaseStrategy[HPAStrategySettings]):
    """
    HPA Optimized Strategy for cost optimization with variable workloads.
    
    Designed for clusters with HPA enabled where usage varies significantly.
    Optimizes costs by sizing requests for minimal pod count during low-traffic periods,
    allowing HPA to scale up during high-traffic periods.
    """

    display_name = "hpa"
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
        max_replicas_info = f"\nMax replicas validation: {'Enabled (' + str(self.settings.max_replicas) + ' replicas)' if self.settings.max_replicas else 'Disabled'}"
        
        s = textwrap.dedent(f"""\
            HPA Optimized Cost-Saving Strategy
            
            CPU request: {self.settings.low_usage_percentile}th percentile / {self.settings.target_pod_count}
            CPU limit: {self.settings.cpu_limit_percent}% of request
            Memory request: {self.settings.low_usage_percentile}th percentile / {self.settings.target_pod_count}
            Memory limit: {self.settings.memory_limit_percent}% of request
            History: {self.settings.history_duration} hours
            Step: {self.settings.timeframe_duration} minutes{max_replicas_info}
            
            This strategy is designed for HPA-enabled deployments with variable usage patterns.
            It optimizes costs by sizing for {self.settings.target_pod_count} pods during low-traffic periods,
            allowing HPA to scale up when needed.

            All parameters can be customized. For example:
            `krr hpa_optimized --low_usage_percentile=40 --target_pod_count=2 --max_replicas=10 --cpu_limit_percent=150 --memory_limit_percent=120`
            
            The --max_replicas parameter validates that your HPA max setting can handle sustained high load (90th percentile).
            Peak spikes above the 90th percentile are handled by the limit percentage.
            If 90th percentile usage ÷ max_replicas > low usage request, it will use the higher value.
            
            Note: This strategy is specifically designed to work WITH HPA and does not skip HPA workloads.
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

        # This strategy is designed for HPA workloads, so we don't skip them

        # Calculate the proposal using our custom logic
        cpu_usage = self.settings.calculate_resource_proposal(data, resource_name="CPU")
        
        # Important: Apply cpu_min_value here to ensure limit percentage is calculated correctly
        # KRR will also apply minimums, but we need to ensure our percentage is based on the actual request
        from robusta_krr.core.models.config import settings as krr_settings
        cpu_min_cores = krr_settings.cpu_min_value / 1000  # Convert from millicores to cores
        cpu_usage = max(cpu_usage, cpu_min_cores)
        
        # Calculate limit as percentage of request (now based on the enforced minimum if applicable)
        cpu_limit = cpu_usage * (self.settings.cpu_limit_percent / 100)
        
        # Return with request and limit (limit can be different based on cpu_limit_percent)
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

        # This strategy is designed for HPA workloads, so we don't skip them

        # Calculate the proposal using our custom logic (now getting total directly from Prometheus)
        memory_usage = self.settings.calculate_resource_proposal(data, resource_name="Memory")
        
        # Important: Apply mem_min here to ensure limit percentage is calculated correctly
        # KRR will also apply minimums, but we need to ensure our percentage is based on the actual request
        from robusta_krr.core.models.config import settings as krr_settings
        memory_min_bytes = krr_settings.memory_min_value * (1024**2)  # Convert from MiB to bytes
        memory_usage = max(memory_usage, memory_min_bytes)
        
        # Calculate limit as percentage of request (now based on the enforced minimum if applicable)
        memory_limit = memory_usage * (self.settings.memory_limit_percent / 100)
        
        # Return with request and limit (limit can be different based on memory_limit_percent)
        return ResourceRecommendation(request=memory_usage, limit=memory_limit)

    def run(self, history_data: MetricsPodData, object_data: K8sObjectData) -> RunResult:
        """Execute the strategy and return recommendations for both CPU and memory."""
        return {
            ResourceType.CPU: self.__calculate_cpu_proposal(history_data, object_data),
            ResourceType.Memory: self.__calculate_memory_proposal(history_data, object_data),
        }
