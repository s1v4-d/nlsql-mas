output "cluster_id" {
  description = "ECS cluster ID"
  value       = aws_ecs_cluster.main.id
}

output "cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "service_discovery_namespace_id" {
  description = "Service Discovery HTTP namespace ID"
  value       = aws_service_discovery_http_namespace.main.id
}

output "service_discovery_namespace_arn" {
  description = "Service Discovery HTTP namespace ARN"
  value       = aws_service_discovery_http_namespace.main.arn
}

output "ecr_repository_urls" {
  description = "Map of service name to ECR repository URLs"
  value       = { for k, v in aws_ecr_repository.services : k => v.repository_url }
}

output "ecr_repository_arns" {
  description = "Map of service name to ECR repository ARNs"
  value       = { for k, v in aws_ecr_repository.services : k => v.arn }
}

output "alb_id" {
  description = "Application Load Balancer ID"
  value       = aws_lb.main.id
}

output "alb_arn" {
  description = "Application Load Balancer ARN"
  value       = aws_lb.main.arn
}

output "alb_arn_suffix" {
  description = "ALB ARN suffix for CloudWatch metrics"
  value       = aws_lb.main.arn_suffix
}

output "alb_dns_name" {
  description = "Application Load Balancer DNS name"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "ALB Route53 zone ID"
  value       = aws_lb.main.zone_id
}

output "alb_url" {
  description = "ALB URL (HTTP or HTTPS based on configuration)"
  value       = var.enable_https ? "https://${aws_lb.main.dns_name}" : "http://${aws_lb.main.dns_name}"
}

output "target_group_arns" {
  description = "Map of service name to target group ARNs"
  value       = { for k, v in aws_lb_target_group.services : k => v.arn }
}

output "target_group_arn_suffixes" {
  description = "Map of service name to target group ARN suffixes"
  value       = { for k, v in aws_lb_target_group.services : k => v.arn_suffix }
}

output "service_ids" {
  description = "Map of service name to ECS service IDs"
  value       = { for k, v in aws_ecs_service.services : k => v.id }
}

output "service_names" {
  description = "Map of service name to ECS service names"
  value       = { for k, v in aws_ecs_service.services : k => v.name }
}

output "task_definition_arns" {
  description = "Map of service name to task definition ARNs"
  value       = { for k, v in aws_ecs_task_definition.services : k => v.arn }
}

output "task_definition_families" {
  description = "Map of service name to task definition families"
  value       = { for k, v in aws_ecs_task_definition.services : k => v.family }
}

output "task_execution_role_arn" {
  description = "Task execution role ARN"
  value       = aws_iam_role.task_execution.arn
}

output "task_execution_role_name" {
  description = "Task execution role name"
  value       = aws_iam_role.task_execution.name
}

output "task_role_arn" {
  description = "Task role ARN"
  value       = aws_iam_role.task.arn
}

output "task_role_name" {
  description = "Task role name"
  value       = aws_iam_role.task.name
}

output "log_group_names" {
  description = "Map of service name to CloudWatch log group names"
  value       = { for k, v in aws_cloudwatch_log_group.services : k => v.name }
}

output "log_group_arns" {
  description = "Map of service name to CloudWatch log group ARNs"
  value       = { for k, v in aws_cloudwatch_log_group.services : k => v.arn }
}

output "ecs_exec_log_group_name" {
  description = "ECS Exec log group name"
  value       = aws_cloudwatch_log_group.ecs_exec.name
}

output "autoscaling_target_resource_ids" {
  description = "Map of service name to auto scaling target resource IDs"
  value       = { for k, v in aws_appautoscaling_target.services : k => v.resource_id }
}
