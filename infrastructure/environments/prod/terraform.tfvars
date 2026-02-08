# Production Environment Variables
# ----------------------------------
# Override defaults for prod environment

project_name = "nlsql"
environment  = "prod"
aws_region   = "us-east-1"

# VPC Configuration - High Availability
vpc_cidr                 = "10.0.0.0/16"
availability_zones_count = 3
single_nat_gateway       = false

# Security and Compliance
enable_vpc_endpoints    = true
enable_vpc_flow_logs    = true
flow_log_retention_days = 90

# S3 Configuration - Full Features
enable_versioning          = false
enable_intelligent_tiering = true
enable_access_logging      = true
use_customer_managed_key   = true

# Common Tags
tags = {
  CostCenter  = "production"
  Owner       = "platform-team"
  Application = "nlsql-mas"
  Compliance  = "soc2"
}
