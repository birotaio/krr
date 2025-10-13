#!/usr/bin/env python3
"""
Script to update resource configurations in deployment config files
based on a YAML file with resource recommendations.

Usage:
    ./update_deployment.py <yaml_file> <env_name> [--exclude service1,service2,...]
    
Arguments:
    yaml_file: Path to the YAML file containing resource configurations
    env_name: Target environment name (e.g., zoov-prod, zoov-staging, theta-prod)
    --exclude: Comma-separated list of services to exclude (optional)

Example:
    ./update_deployment.py ../generated/prod.yaml zoov-prod --exclude event-data-transformer,gateway-wirma
"""

import yaml
import os
import sys
import argparse
from pathlib import Path

def load_staging_resources(yaml_file):
    """Load resource configurations from the specified YAML file"""
    try:
        yaml_path = Path(yaml_file)
        if not yaml_path.exists():
            print(f"Error: {yaml_file} not found!")
            return {}
            
        with open(yaml_path, 'r') as f:
            staging_data = yaml.safe_load(f)
        
        resources = {}
        for deployment in staging_data.get('deployments', []):
            for service_name, config in deployment.items():
                if 'resources' in config:
                    resources[service_name] = config['resources']
        
        return resources
    except Exception as e:
        print(f"Error loading {yaml_file}: {e}")
        return {}

def update_service_config(config_file, new_resources):
    """Update the resources section in a service config file while preserving formatting"""
    try:
        # Read the current config file
        with open(config_file, 'r') as f:
            lines = f.readlines()
        
        # Find the resources section
        resources_start = None
        resources_end = None
        indent_level = None
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == 'resources:':
                resources_start = i
                # Determine the indentation level
                indent_level = len(line) - len(line.lstrip())
                
                # Find the end of the resources section
                for j in range(i + 1, len(lines)):
                    next_line = lines[j]
                    if next_line.strip() == '':
                        continue
                    next_indent = len(next_line) - len(next_line.lstrip())
                    # If we find a line with same or less indentation that's not empty, resources section ends
                    if next_indent <= indent_level and next_line.strip():
                        resources_end = j
                        break
                else:
                    # Resources section goes to end of file
                    resources_end = len(lines)
                break
        
        if resources_start is None:
            # No resources section found, add it at the end
            if lines and not lines[-1].endswith('\n'):
                lines.append('\n')
            lines.append('resources:\n')
            resources_start = len(lines) - 1
            resources_end = len(lines)
            indent_level = 0
        
        # Generate the new resources section with proper indentation
        base_indent = ' ' * indent_level
        resource_indent = ' ' * (indent_level + 2)
        value_indent = ' ' * (indent_level + 4)
        
        new_resources_lines = [f"{base_indent}resources:\n"]
        
        # Add requests section
        if 'requests' in new_resources:
            new_resources_lines.append(f"{resource_indent}requests:\n")
            for key, value in new_resources['requests'].items():
                new_resources_lines.append(f"{value_indent}{key}: {value}\n")
        
        # Add limits section
        if 'limits' in new_resources:
            new_resources_lines.append(f"{resource_indent}limits:\n")
            for key, value in new_resources['limits'].items():
                new_resources_lines.append(f"{value_indent}{key}: {value}\n")
        
        # Replace the resources section
        updated_lines = lines[:resources_start] + new_resources_lines + lines[resources_end:]
        
        # Write back to file
        with open(config_file, 'w') as f:
            f.writelines(updated_lines)
        
        return True
    except Exception as e:
        print(f"Error updating {config_file}: {e}")
        return False

def main():
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description='Update resource configurations in deployment config files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ../generated/prod.yaml zoov-prod
  %(prog)s prod.yaml zoov-staging --exclude event-data-transformer,gateway-wirma
  %(prog)s ./generated/partners.yaml zoov-partners-prod
        """
    )
    parser.add_argument('yaml_file', help='Path to the YAML file containing resource configurations')
    parser.add_argument('env_name', help='Target environment name (e.g., zoov-prod, theta-prod)')
    parser.add_argument('--exclude', help='Comma-separated list of services to exclude', default='')
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    yaml_file = Path(args.yaml_file)
    env_name = args.env_name
    
    # Parse exclusion list
    excluded_services = set()
    if args.exclude:
        excluded_services = set(s.strip() for s in args.exclude.split(',') if s.strip())
    
    # Resolve yaml file path (can be absolute or relative to script)
    if not yaml_file.is_absolute():
        yaml_file = script_dir / yaml_file
    
    # Target directory is ../../backend-deployments/{env_name}/configs
    # (script is in krr/script, so we go up two levels to reach the parent of krr)
    config_dir = script_dir.parent.parent / 'backend-deployments' / env_name / 'configs'
    
    # Check if YAML file exists
    if not yaml_file.exists():
        print(f"Error: {yaml_file} not found!")
        sys.exit(1)
    
    # Check if target directory exists
    if not config_dir.exists():
        print(f"Error: {config_dir} not found!")
        print(f"Make sure the environment '{env_name}' exists in ../../backend-deployments/")
        sys.exit(1)
    
    # Load resources from YAML file
    print(f"Loading resource configurations from {yaml_file}...")
    staging_resources = load_staging_resources(yaml_file)
    
    if not staging_resources:
        print(f"No resource configurations found in {yaml_file}")
        sys.exit(1)
    
    print(f"Found {len(staging_resources)} service configurations")
    print(f"Target environment: {env_name}")
    print(f"Target directory: {config_dir}")
    if excluded_services:
        print(f"Excluded services: {', '.join(sorted(excluded_services))}")
    
    # Process each service
    updated_count = 0
    skipped_count = 0
    
    for service_name, resources in staging_resources.items():
        # Check if service is in exclusion list
        if service_name in excluded_services:
            print(f"Skipping {service_name} (excluded)")
            skipped_count += 1
            continue
            
        config_file = config_dir / f"{service_name}.yaml"
        
        if config_file.exists():
            print(f"Updating {service_name}.yaml...")
            if update_service_config(config_file, resources):
                updated_count += 1
                print(f"  ✓ Successfully updated {service_name}.yaml")
            else:
                print(f"  ✗ Failed to update {service_name}.yaml")
        else:
            print(f"Skipping {service_name}.yaml (file not found in {env_name})")
            skipped_count += 1
    
    print(f"\nSummary:")
    print(f"  Updated: {updated_count} files")
    print(f"  Skipped: {skipped_count} files")
    print(f"\nDon't forget to commit and push the changes in the backend-deployments repository!")

if __name__ == "__main__":
    main()
