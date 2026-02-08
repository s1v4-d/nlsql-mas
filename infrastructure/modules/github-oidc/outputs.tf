output "oidc_provider_arn" {
  description = "GitHub OIDC provider ARN"
  value       = aws_iam_openid_connect_provider.github.arn
}

output "oidc_provider_url" {
  description = "GitHub OIDC provider URL"
  value       = aws_iam_openid_connect_provider.github.url
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions (general use)"
  value       = aws_iam_role.github_actions.arn
}

output "github_actions_role_name" {
  description = "IAM role name for GitHub Actions (general use)"
  value       = aws_iam_role.github_actions.name
}

output "terraform_role_arn" {
  description = "IAM role ARN for Terraform operations"
  value       = aws_iam_role.github_actions_terraform.arn
}

output "terraform_role_name" {
  description = "IAM role name for Terraform operations"
  value       = aws_iam_role.github_actions_terraform.name
}

output "terraform_prod_role_arn" {
  description = "IAM role ARN for production Terraform operations (main branch only)"
  value       = var.create_prod_role ? aws_iam_role.github_actions_terraform_prod[0].arn : null
}

output "prod_role_arn" {
  description = "IAM role ARN for production deployments (main branch only)"
  value       = var.create_prod_role ? aws_iam_role.github_actions_prod[0].arn : null
}

output "workflow_configuration" {
  description = "Configuration values for GitHub Actions workflows"
  value = {
    general_role_arn   = aws_iam_role.github_actions.arn
    terraform_role_arn = aws_iam_role.github_actions_terraform.arn
    prod_role_arn      = var.create_prod_role ? aws_iam_role.github_actions_prod[0].arn : null
    terraform_prod_arn = var.create_prod_role ? aws_iam_role.github_actions_terraform_prod[0].arn : null
  }
}
