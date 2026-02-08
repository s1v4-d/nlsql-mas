# Retail Insights Assistant - Infrastructure

Terraform infrastructure for deploying the NL-SQL Multi-Agent System on AWS.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         AWS Cloud                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    VPC (10.0.0.0/16)                      │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐         │  │
│  │  │ Public AZ-a │ │ Public AZ-b │ │ Public AZ-c │         │  │
│  │  │   ALB, NAT  │ │   ALB, NAT  │ │   ALB, NAT  │         │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘         │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐         │  │
│  │  │Private AZ-a │ │Private AZ-b │ │Private AZ-c │         │  │
│  │  │ ECS Fargate │ │ ECS Fargate │ │ ECS Fargate │         │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘         │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐         │  │
│  │  │Database AZ-a│ │Database AZ-b│ │Database AZ-c│         │  │
│  │  │   Aurora    │ │   Aurora    │ │   Aurora    │         │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                    ┌─────────▼─────────┐                        │
│                    │   S3 Data Lake   │                         │
│                    │  (100GB+ Parquet) │                        │
│                    └───────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

## Modules

| Module | Description |
|--------|-------------|
| `networking` | VPC, subnets, NAT Gateway, security groups, VPC endpoints |
| `s3` | S3 data lake, KMS encryption, lifecycle policies |
| `ecs` | ECS cluster, task definitions, services, ALB (TODO) |
| `aurora` | Aurora PostgreSQL Serverless v2 with pgvector (TODO) |

## Directory Structure

```
infrastructure/
├── modules/
│   ├── networking/     # VPC, subnets, security groups
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── versions.tf
│   ├── s3/             # S3 data lake
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── versions.tf
│   ├── ecs/            # ECS Fargate (TODO)
│   └── aurora/         # Aurora PostgreSQL (TODO)
├── environments/
│   ├── dev/
│   │   ├── main.tf
│   │   ├── terraform.tfvars
│   │   └── backend.tf
│   └── prod/
│       ├── main.tf
│       ├── terraform.tfvars
│       └── backend.tf
└── README.md
```

## Prerequisites

1. **Terraform >= 1.5.0**
2. **AWS CLI** configured with appropriate credentials
3. **S3 bucket** for Terraform state (create manually first)
4. **DynamoDB table** for state locking (create manually first)

### Create State Backend (One-time setup)

```bash
# Create S3 bucket for state
aws s3api create-bucket \
  --bucket nlsql-terraform-state \
  --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket nlsql-terraform-state \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for locking
aws dynamodb create-table \
  --table-name nlsql-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

## Quick Start

### Development Environment

```bash
cd infrastructure/environments/dev

# Initialize Terraform
terraform init

# Review plan
terraform plan

# Apply infrastructure
terraform apply
```

### Production Environment

```bash
cd infrastructure/environments/prod

# Initialize Terraform
terraform init

# Review plan
terraform plan -var-file=terraform.tfvars

# Apply infrastructure
terraform apply -var-file=terraform.tfvars
```

## Environment Differences

| Feature | Dev | Prod |
|---------|-----|------|
| VPC CIDR | 10.2.0.0/16 | 10.0.0.0/16 |
| Availability Zones | 2 | 3 |
| NAT Gateway | Single (cost savings) | Multi-AZ (HA) |
| VPC Endpoints | Disabled | Enabled |
| Flow Logs Retention | 7 days | 90 days |
| S3 Encryption | AES256 | KMS CMK |
| S3 Intelligent Tiering | Disabled | Enabled |
| Access Logging | Disabled | Enabled |

## Security Groups

| Security Group | Purpose | Inbound | Outbound |
|----------------|---------|---------|----------|
| `alb-sg` | Application Load Balancer | 80, 443 from 0.0.0.0/0 | 8000, 8501 to ECS |
| `ecs-tasks-sg` | ECS Fargate tasks | 8000, 8501 from ALB | 5432 to Aurora, 443 to internet |
| `aurora-sg` | Aurora PostgreSQL | 5432 from ECS | None |
| `vpc-endpoints-sg` | VPC endpoints | 443 from VPC | None |

## Cost Optimization

### Development (~$50-100/month)
- Single NAT Gateway
- No VPC endpoints (use NAT for AWS services)
- S3 Standard storage
- Minimal logging

### Production (~$300-500/month)
- Multi-AZ NAT Gateway ($98/month)
- VPC endpoints ($88/month) - saves NAT data processing
- S3 Intelligent Tiering (auto-optimize)
- Full logging and monitoring

## Tagging Strategy

All resources are tagged with:
- `Project`: nlsql
- `Environment`: dev/staging/prod
- `ManagedBy`: terraform
- `Module`: networking/s3/ecs/aurora

## Troubleshooting

### State Lock Issues
```bash
# Force unlock (use with caution)
terraform force-unlock <LOCK_ID>
```

### Plan Shows Unexpected Changes
```bash
# Refresh state from AWS
terraform refresh
```

### Module Not Found
```bash
# Reinitialize modules
terraform init -upgrade
```

## Next Steps

- [ ] TICKET-019: ECS Fargate module
- [ ] TICKET-020: Aurora PostgreSQL module
- [ ] TICKET-021: (Done) S3 Data Lake module
- [ ] TICKET-022: Environment composition
- [ ] TICKET-023: CI/CD with GitHub Actions
