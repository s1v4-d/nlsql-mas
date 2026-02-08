output "cluster_id" {
  description = "Aurora cluster ID"
  value       = aws_rds_cluster.aurora.id
}

output "cluster_arn" {
  description = "Aurora cluster ARN"
  value       = aws_rds_cluster.aurora.arn
}

output "cluster_identifier" {
  description = "Aurora cluster identifier"
  value       = aws_rds_cluster.aurora.cluster_identifier
}

output "cluster_resource_id" {
  description = "Aurora cluster resource ID (for IAM authentication)"
  value       = aws_rds_cluster.aurora.cluster_resource_id
}

output "cluster_endpoint" {
  description = "Aurora cluster endpoint (writer)"
  value       = aws_rds_cluster.aurora.endpoint
}

output "cluster_reader_endpoint" {
  description = "Aurora cluster reader endpoint"
  value       = aws_rds_cluster.aurora.reader_endpoint
}

output "cluster_port" {
  description = "Aurora cluster port"
  value       = aws_rds_cluster.aurora.port
}

output "database_name" {
  description = "Default database name"
  value       = aws_rds_cluster.aurora.database_name
}

output "master_username" {
  description = "Master username"
  value       = aws_rds_cluster.aurora.master_username
}

output "writer_instance_id" {
  description = "Writer instance ID"
  value       = aws_rds_cluster_instance.writer.id
}

output "writer_instance_arn" {
  description = "Writer instance ARN"
  value       = aws_rds_cluster_instance.writer.arn
}

output "writer_instance_endpoint" {
  description = "Writer instance endpoint"
  value       = aws_rds_cluster_instance.writer.endpoint
}

output "reader_instance_ids" {
  description = "List of reader instance IDs"
  value       = aws_rds_cluster_instance.readers[*].id
}

output "reader_instance_endpoints" {
  description = "List of reader instance endpoints"
  value       = aws_rds_cluster_instance.readers[*].endpoint
}

output "master_secret_arn" {
  description = "Master user secret ARN"
  value       = aws_rds_cluster.aurora.master_user_secret[0].secret_arn
}

output "app_credentials_secret_arn" {
  description = "Application credentials secret ARN"
  value       = var.create_app_user_secret ? aws_secretsmanager_secret.app_credentials[0].arn : null
}

output "app_credentials_secret_name" {
  description = "Application credentials secret name"
  value       = var.create_app_user_secret ? aws_secretsmanager_secret.app_credentials[0].name : null
}

output "connection_info" {
  description = "Database connection information"
  value = {
    host          = aws_rds_cluster.aurora.endpoint
    reader_host   = aws_rds_cluster.aurora.reader_endpoint
    port          = aws_rds_cluster.aurora.port
    database      = aws_rds_cluster.aurora.database_name
    username      = aws_rds_cluster.aurora.master_username
    ssl_required  = true
    engine        = "aurora-postgresql"
    engine_version = aws_rds_cluster.aurora.engine_version
  }
}

output "jdbc_connection_string" {
  description = "JDBC connection string template"
  value       = "jdbc:postgresql://${aws_rds_cluster.aurora.endpoint}:${aws_rds_cluster.aurora.port}/${aws_rds_cluster.aurora.database_name}?sslmode=require"
}

output "python_connection_string" {
  description = "Python/SQLAlchemy connection string template (use with Secrets Manager)"
  value       = "postgresql+psycopg://<user>:<password>@${aws_rds_cluster.aurora.endpoint}:${aws_rds_cluster.aurora.port}/${aws_rds_cluster.aurora.database_name}?sslmode=require"
}

output "db_subnet_group_name" {
  description = "DB subnet group name"
  value       = aws_db_subnet_group.aurora.name
}

output "db_subnet_group_arn" {
  description = "DB subnet group ARN"
  value       = aws_db_subnet_group.aurora.arn
}

output "cluster_parameter_group_name" {
  description = "Cluster parameter group name"
  value       = aws_rds_cluster_parameter_group.aurora.name
}

output "instance_parameter_group_name" {
  description = "Instance parameter group name"
  value       = aws_db_parameter_group.aurora.name
}

output "kms_key_arn" {
  description = "KMS key ARN used for encryption"
  value       = local.kms_key_arn
}

output "kms_key_id" {
  description = "KMS key ID (if created by this module)"
  value       = var.kms_key_arn == null ? aws_kms_key.aurora[0].key_id : null
}

output "aurora_connect_policy_arn" {
  description = "IAM policy ARN for Aurora connection"
  value       = aws_iam_policy.aurora_connect.arn
}

output "monitoring_role_arn" {
  description = "Enhanced monitoring IAM role ARN"
  value       = var.enhanced_monitoring_interval > 0 ? aws_iam_role.rds_monitoring[0].arn : null
}

output "cloudwatch_log_groups" {
  description = "Map of CloudWatch log group names"
  value       = { for k, v in aws_cloudwatch_log_group.aurora : k => v.name }
}

output "sns_topic_arn" {
  description = "SNS topic ARN for Aurora events"
  value       = aws_sns_topic.aurora_events.arn
}

output "cloudwatch_alarm_arns" {
  description = "CloudWatch alarm ARNs"
  value = {
    cpu         = aws_cloudwatch_metric_alarm.cpu_utilization.arn
    connections = aws_cloudwatch_metric_alarm.database_connections.arn
    memory      = aws_cloudwatch_metric_alarm.freeable_memory.arn
    acu         = aws_cloudwatch_metric_alarm.acu_utilization.arn
  }
}

output "scaling_configuration" {
  description = "Serverless v2 scaling configuration"
  value = {
    min_capacity = var.min_capacity
    max_capacity = var.max_capacity
    storage_type = var.storage_type
  }
}
