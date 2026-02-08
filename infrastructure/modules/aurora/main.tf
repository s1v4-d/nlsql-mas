data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    Module      = "aurora"
    ManagedBy   = "terraform"
  })

  # Engine family for parameter group
  engine_family = "aurora-postgresql${split(".", var.engine_version)[0]}"

  # Use managed KMS or provided key
  kms_key_arn = var.kms_key_arn != null ? var.kms_key_arn : aws_kms_key.aurora[0].arn
}

# KMS Key (if not provided)

resource "aws_kms_key" "aurora" {
  count = var.kms_key_arn == null ? 1 : 0

  description             = "KMS key for Aurora ${local.name_prefix} encryption"
  deletion_window_in_days = var.environment == "prod" ? 30 : 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow RDS to use the key"
        Effect = "Allow"
        Principal = {
          Service = "rds.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-kms"
  })
}

resource "aws_kms_alias" "aurora" {
  count = var.kms_key_arn == null ? 1 : 0

  name          = "alias/${local.name_prefix}-aurora"
  target_key_id = aws_kms_key.aurora[0].key_id
}

resource "aws_db_subnet_group" "aurora" {
  name        = "${local.name_prefix}-aurora"
  description = "Aurora subnet group for ${local.name_prefix}"
  subnet_ids  = var.database_subnet_ids

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-subnet-group"
  })
}

# Cluster Parameter Group (with pgvector support)
resource "aws_rds_cluster_parameter_group" "aurora" {
  name        = "${local.name_prefix}-cluster-pg"
  family      = local.engine_family
  description = "Aurora PostgreSQL cluster parameter group with pgvector optimization"

  # pgvector extension support
  dynamic "parameter" {
    for_each = var.enable_pgvector ? [1] : []
    content {
      name         = "shared_preload_libraries"
      value        = "pg_stat_statements,pgvector"
      apply_method = "pending-reboot"
    }
  }

  # Memory settings for vector operations
  parameter {
    name  = "work_mem"
    value = "262144" # 256MB in KB
  }

  parameter {
    name  = "maintenance_work_mem"
    value = "524288" # 512MB in KB
  }

  # Connection settings for LangGraph checkpointing
  parameter {
    name  = "idle_in_transaction_session_timeout"
    value = "60000" # 60 seconds
  }

  # Query performance
  parameter {
    name  = "random_page_cost"
    value = "1.1"
  }

  parameter {
    name  = "effective_io_concurrency"
    value = "200"
  }

  # Logging
  parameter {
    name  = "log_statement"
    value = var.environment == "prod" ? "ddl" : "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = tostring(var.log_min_duration_statement)
  }

  parameter {
    name  = "log_lock_waits"
    value = "1"
  }

  # Checkpointing optimization
  parameter {
    name  = "checkpoint_timeout"
    value = "900" # 15 minutes
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cluster-pg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# Instance Parameter Group
resource "aws_db_parameter_group" "aurora" {
  name        = "${local.name_prefix}-instance-pg"
  family      = local.engine_family
  description = "Aurora PostgreSQL instance parameter group"

  parameter {
    name  = "log_temp_files"
    value = "0" # Log all temp file usage
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-instance-pg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_iam_role" "rds_monitoring" {
  count = var.enhanced_monitoring_interval > 0 ? 1 : 0

  name = "${local.name_prefix}-rds-monitoring"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "monitoring.rds.amazonaws.com"
      }
    }]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds-monitoring-role"
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  count = var.enhanced_monitoring_interval > 0 ? 1 : 0

  role       = aws_iam_role.rds_monitoring[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

resource "aws_rds_cluster" "aurora" {
  cluster_identifier = local.name_prefix
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = var.engine_version
  database_name      = var.database_name
  master_username    = var.master_username
  port               = var.port

  # Secrets Manager managed password
  manage_master_user_password   = true
  master_user_secret_kms_key_id = local.kms_key_arn

    serverlessv2_scaling_configuration {
    min_capacity = var.min_capacity
    max_capacity = var.max_capacity
  }

  # Networking
  db_subnet_group_name   = aws_db_subnet_group.aurora.name
  vpc_security_group_ids = [var.aurora_security_group_id]

    storage_encrypted = true
  kms_key_id        = local.kms_key_arn
  storage_type      = var.storage_type

    backup_retention_period   = var.backup_retention_period
  preferred_backup_window   = var.preferred_backup_window
  copy_tags_to_snapshot     = true

  # Maintenance
  preferred_maintenance_window = var.preferred_maintenance_window

  # Logging
  enabled_cloudwatch_logs_exports = var.enabled_cloudwatch_logs_exports

  # Protection
  deletion_protection = var.deletion_protection
  skip_final_snapshot = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${local.name_prefix}-final-${formatdate("YYYYMMDD-hhmmss", timestamp())}"

  # IAM authentication
  iam_database_authentication_enabled = var.iam_database_authentication_enabled

  # Parameter group
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.aurora.name

    apply_immediately = var.apply_immediately

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-cluster"
  })

  lifecycle {
    ignore_changes = [
      final_snapshot_identifier,
      master_password,
    ]
  }

  depends_on = [aws_cloudwatch_log_group.aurora]
}

resource "aws_cloudwatch_log_group" "aurora" {
  for_each = toset(var.enabled_cloudwatch_logs_exports)

  name              = "/aws/rds/cluster/${local.name_prefix}/${each.key}"
  retention_in_days = var.environment == "prod" ? 90 : 30
  kms_key_id        = local.kms_key_arn

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-${each.key}-logs"
  })
}

# Writer Instance
resource "aws_rds_cluster_instance" "writer" {
  identifier         = "${local.name_prefix}-writer"
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.aurora.engine
  engine_version     = aws_rds_cluster.aurora.engine_version

  # Parameter group
  db_parameter_group_name = aws_db_parameter_group.aurora.name

  # Performance Insights
  performance_insights_enabled          = var.performance_insights_enabled
  performance_insights_kms_key_id       = var.performance_insights_enabled ? local.kms_key_arn : null
  performance_insights_retention_period = var.performance_insights_enabled ? var.performance_insights_retention : null

  # Enhanced monitoring
  monitoring_interval = var.enhanced_monitoring_interval
  monitoring_role_arn = var.enhanced_monitoring_interval > 0 ? aws_iam_role.rds_monitoring[0].arn : null

  # Auto minor version upgrade
  auto_minor_version_upgrade = true

  # Failover priority (0 = highest)
  promotion_tier = 0

    apply_immediately = var.apply_immediately

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-writer"
    Role = "writer"
  })
}

# Reader Instances
resource "aws_rds_cluster_instance" "readers" {
  count = var.reader_count

  identifier         = "${local.name_prefix}-reader-${count.index + 1}"
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.aurora.engine
  engine_version     = aws_rds_cluster.aurora.engine_version

  db_parameter_group_name = aws_db_parameter_group.aurora.name

  performance_insights_enabled          = var.performance_insights_enabled
  performance_insights_kms_key_id       = var.performance_insights_enabled ? local.kms_key_arn : null
  performance_insights_retention_period = var.performance_insights_enabled ? var.performance_insights_retention : null

  monitoring_interval = var.enhanced_monitoring_interval
  monitoring_role_arn = var.enhanced_monitoring_interval > 0 ? aws_iam_role.rds_monitoring[0].arn : null

  auto_minor_version_upgrade = true

  # Failover priority (higher = lower priority)
  promotion_tier = count.index + 1

  apply_immediately = var.apply_immediately

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-reader-${count.index + 1}"
    Role = "reader"
  })
}

# Application User Credentials (Secrets Manager)

resource "random_password" "app_user" {
  count = var.create_app_user_secret ? 1 : 0

  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "app_credentials" {
  count = var.create_app_user_secret ? 1 : 0

  name        = "${var.project_name}/${var.environment}/database/app-credentials"
  description = "Application database credentials for ${local.name_prefix}"
  kms_key_id  = local.kms_key_arn

  recovery_window_in_days = var.environment == "prod" ? 30 : 7

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-app-db-credentials"
  })
}

resource "aws_secretsmanager_secret_version" "app_credentials" {
  count = var.create_app_user_secret ? 1 : 0

  secret_id = aws_secretsmanager_secret.app_credentials[0].id
  secret_string = jsonencode({
    username       = var.app_username
    password       = random_password.app_user[0].result
    host           = aws_rds_cluster.aurora.endpoint
    reader_host    = aws_rds_cluster.aurora.reader_endpoint
    port           = var.port
    dbname         = var.database_name
    engine         = "postgresql"
    connection_url = "postgresql://${var.app_username}:${random_password.app_user[0].result}@${aws_rds_cluster.aurora.endpoint}:${var.port}/${var.database_name}?sslmode=require"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_cloudwatch_metric_alarm" "cpu_utilization" {
  alarm_name          = "${local.name_prefix}-aurora-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Aurora CPU utilization is above 80%"

  dimensions = {
    DBClusterIdentifier = aws_rds_cluster.aurora.cluster_identifier
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-cpu-alarm"
  })
}

resource "aws_cloudwatch_metric_alarm" "database_connections" {
  alarm_name          = "${local.name_prefix}-aurora-high-connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = var.environment == "prod" ? 500 : 100
  alarm_description   = "Aurora database connections are high"

  dimensions = {
    DBClusterIdentifier = aws_rds_cluster.aurora.cluster_identifier
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-connections-alarm"
  })
}

resource "aws_cloudwatch_metric_alarm" "freeable_memory" {
  alarm_name          = "${local.name_prefix}-aurora-low-memory"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 3
  metric_name         = "FreeableMemory"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = 256000000 # 256MB
  alarm_description   = "Aurora freeable memory is below 256MB"

  dimensions = {
    DBClusterIdentifier = aws_rds_cluster.aurora.cluster_identifier
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-memory-alarm"
  })
}

resource "aws_cloudwatch_metric_alarm" "acu_utilization" {
  alarm_name          = "${local.name_prefix}-aurora-high-acu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 5
  metric_name         = "ACUUtilization"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = 90
  alarm_description   = "Aurora ACU utilization is above 90% - consider increasing max ACU"

  dimensions = {
    DBClusterIdentifier = aws_rds_cluster.aurora.cluster_identifier
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-acu-alarm"
  })
}

resource "aws_sns_topic" "aurora_events" {
  name              = "${local.name_prefix}-aurora-events"
  kms_master_key_id = local.kms_key_arn

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-events"
  })
}

resource "aws_db_event_subscription" "aurora" {
  name      = "${local.name_prefix}-aurora-events"
  sns_topic = aws_sns_topic.aurora_events.arn

  source_type = "db-cluster"
  source_ids  = [aws_rds_cluster.aurora.id]

  event_categories = [
    "failover",
    "failure",
    "maintenance",
    "notification",
    "recovery",
  ]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-aurora-event-sub"
  })
}

resource "aws_iam_policy" "aurora_connect" {
  name        = "${local.name_prefix}-aurora-connect"
  description = "IAM policy for connecting to Aurora PostgreSQL"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds-db:connect"
        ]
        Resource = [
          "arn:${data.aws_partition.current.partition}:rds-db:${var.aws_region}:${data.aws_caller_identity.current.account_id}:dbuser:${aws_rds_cluster.aurora.cluster_resource_id}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = compact([
          aws_rds_cluster.aurora.master_user_secret[0].secret_arn,
          var.create_app_user_secret ? aws_secretsmanager_secret.app_credentials[0].arn : ""
        ])
      }
    ]
  })

  tags = local.common_tags
}
