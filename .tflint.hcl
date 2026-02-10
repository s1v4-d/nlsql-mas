# TFLint Configuration
# See: https://github.com/terraform-linters/tflint

config {
  format = "compact"

  call_module_type    = "local"
  force               = false
  disabled_by_default = false
}

# AWS Provider Plugin
plugin "aws" {
  enabled = true
  version = "0.33.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

# Terraform Core Rules
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

# Naming Convention - enforce snake_case
rule "terraform_naming_convention" {
  enabled = true
  format  = "snake_case"
}

# Require variable descriptions
rule "terraform_documented_variables" {
  enabled = true
}

# Require output descriptions
rule "terraform_documented_outputs" {
  enabled = true
}

# Detect unused declarations
rule "terraform_unused_declarations" {
  enabled = true
}

# Require variable types
rule "terraform_typed_variables" {
  enabled = true
}

# Prevent deprecated syntax
rule "terraform_deprecated_interpolation" {
  enabled = true
}

# Standard module structure
rule "terraform_standard_module_structure" {
  enabled = true
}

# Comment syntax
rule "terraform_comment_syntax" {
  enabled = true
}

# AWS-specific rules

# Validate EC2 instance types
rule "aws_instance_invalid_type" {
  enabled = true
}

# Validate ECS Fargate CPU/Memory combinations
rule "aws_ecs_task_definition_invalid_cpu" {
  enabled = true
}

# Require tags on resources
rule "aws_resource_missing_tags" {
  enabled = true
  tags    = ["Environment", "Project", "ManagedBy"]

  exclude = [
    "aws_iam_policy",
    "aws_iam_role_policy",
    "aws_iam_policy_attachment",
  ]
}

# Security group rules
rule "aws_security_group_inline_rules_disabled" {
  enabled = true
}

# Validate RDS instance types
rule "aws_db_instance_invalid_type" {
  enabled = true
}
