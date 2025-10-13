"""
Custom YAML formatter for KRR recommendations.
Outputs only computed resource values in a clean YAML format.
"""

from robusta_krr.core.abstract import formatters
from robusta_krr.core.models.result import Result, ResourceType
from robusta_krr.utils import resource_units


def _format_resource_value(value, resource_type: ResourceType) -> str:
    """Format a resource value to string (e.g., '100m' for CPU, '256Mi' for memory)."""
    if value is None:
        return "null"
    
    # Handle unknown/NaN values (represented as "?")
    if isinstance(value, str):
        return "null"
    
    # Value is stored as float (raw millicores or bytes)
    # For CPU: format with base 1000 (m, k, M, G)
    # For Memory: format with base 1024 (Ki, Mi, Gi)
    if resource_type == ResourceType.CPU:
        return resource_units.format(value, base=1000)
    elif resource_type == ResourceType.Memory:
        return resource_units.format(value, base=1024)
    else:
        return str(value)

@formatters.register("ready-to-deploy")
def ready_to_deploy(result: Result) -> str:
    """
    Simplified YAML format - groups by workload type.
    Matches the exact format requested: deployments with resource recommendations only.
    """
    # Group scans by workload type
    workload_groups: dict[str, dict] = {}
    
    for scan in result.scans:
        obj = scan.object
        workload_type = obj.kind.lower() + "s"  # e.g., "deployment" -> "deployments"
        
        if workload_type not in workload_groups:
            workload_groups[workload_type] = {}
        
        # Use workload name as key (or name-container if multiple containers)
        workload_key = obj.name
        if obj.container and obj.container != obj.name:
            workload_key = f"{obj.name}-{obj.container}"
        
        # Get recommended values
        cpu_request = scan.recommended.requests[ResourceType.CPU].value
        cpu_limit = scan.recommended.limits[ResourceType.CPU].value
        memory_request = scan.recommended.requests[ResourceType.Memory].value
        memory_limit = scan.recommended.limits[ResourceType.Memory].value
        
        workload_groups[workload_type][workload_key] = {
            'cpu_request': cpu_request,
            'cpu_limit': cpu_limit,
            'memory_request': memory_request,
            'memory_limit': memory_limit,
        }
    
    # Build YAML output in your exact format
    lines = []
    
    for workload_type in sorted(workload_groups.keys()):
        lines.append(f"{workload_type}:")
        
        for workload_name, values in workload_groups[workload_type].items():
            lines.append(f"  - {workload_name}:")
            lines.append(f"      resources:")
            lines.append(f"        requests:")
            lines.append(f"          cpu: {_format_resource_value(values['cpu_request'], ResourceType.CPU)}")
            lines.append(f"          memory: {_format_resource_value(values['memory_request'], ResourceType.Memory)}")
            lines.append(f"        limits:")
            lines.append(f"          cpu: {_format_resource_value(values['cpu_limit'], ResourceType.CPU)}")
            lines.append(f"          memory: {_format_resource_value(values['memory_limit'], ResourceType.Memory)}")
    
    return "\n".join(lines)
