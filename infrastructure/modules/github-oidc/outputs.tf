output "oidc_provider_arn" {
  description = "GitHub OIDC provider ARN"
  value       = aws_iam_openid_connect_provider.github.arn
}

output "oidc_provider_url" {
  description = "GitHub OIDC provider URL"
  value       = aws_iam_openid_connect_provider.github.url
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions (ECR, ECS, S3)"
  value       = aws_iam_role.github_actions.arn
}

output "github_actions_role_name" {
  description = "IAM role name for GitHub Actions"
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
