output "application_log_group_name" {
  description = "Name of the application CloudWatch log group"
  value       = aws_cloudwatch_log_group.application.name
}

output "application_log_group_arn" {
  description = "ARN of the application CloudWatch log group"
  value       = aws_cloudwatch_log_group.application.arn
}

output "xray_log_group_name" {
  description = "Name of the X-Ray CloudWatch log group"
  value       = var.enable_xray ? aws_cloudwatch_log_group.xray[0].name : null
}

output "dashboard_url" {
  description = "URL to the CloudWatch dashboard"
  value       = "https://${data.aws_region.current.name}.console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "alarm_arns" {
  description = "Map of alarm names to their ARNs"
  value = {
    api_latency = aws_cloudwatch_metric_alarm.api_latency.arn
    error_rate  = aws_cloudwatch_metric_alarm.error_rate.arn
    ecs_cpu     = aws_cloudwatch_metric_alarm.ecs_cpu_high.arn
    ecs_memory  = aws_cloudwatch_metric_alarm.ecs_memory_high.arn
  }
}
