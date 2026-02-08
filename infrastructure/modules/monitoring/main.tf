locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "monitoring"
  })
}

resource "aws_cloudwatch_log_group" "application" {
  name              = "/ecs/${local.name_prefix}/application"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "xray" {
  count             = var.enable_xray ? 1 : 0
  name              = "/aws/xray/${local.name_prefix}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "${local.name_prefix}-api-latency-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "retail_insights.queries.latency"
  namespace           = "${var.project_name}/Application"
  period              = 60
  statistic           = "Average"
  threshold           = var.api_latency_threshold_ms
  alarm_description   = "API latency exceeds ${var.api_latency_threshold_ms}ms threshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    Environment = var.environment
    Service     = "retail-insights"
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "error_rate" {
  alarm_name          = "${local.name_prefix}-error-rate-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = var.error_rate_threshold_percent

  metric_query {
    id          = "error_rate"
    expression  = "(errors / total) * 100"
    label       = "Error Rate"
    return_data = true
  }

  metric_query {
    id = "errors"
    metric {
      metric_name = "retail_insights.queries.total"
      namespace   = "${var.project_name}/Application"
      period      = 60
      stat        = "Sum"
      dimensions = {
        success = "False"
      }
    }
  }

  metric_query {
    id = "total"
    metric {
      metric_name = "retail_insights.queries.total"
      namespace   = "${var.project_name}/Application"
      period      = 60
      stat        = "Sum"
    }
  }

  alarm_description  = "Query error rate exceeds ${var.error_rate_threshold_percent}%"
  treat_missing_data = "notBreaching"

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "ecs_cpu_high" {
  alarm_name          = "${local.name_prefix}-ecs-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = var.cpu_utilization_threshold
  alarm_description   = "ECS CPU utilization exceeds ${var.cpu_utilization_threshold}%"
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "ecs_memory_high" {
  alarm_name          = "${local.name_prefix}-ecs-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = var.memory_utilization_threshold
  alarm_description   = "ECS memory utilization exceeds ${var.memory_utilization_threshold}%"
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_name
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${local.name_prefix}-overview"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Query Latency (ms)"
          region = data.aws_region.current.name
          metrics = [
            [
              "${var.project_name}/Application",
              "retail_insights.queries.latency",
              "Environment", var.environment,
              { stat = "Average", period = 60 }
            ],
            [
              "...",
              { stat = "p99", period = 60 }
            ]
          ]
          view   = "timeSeries"
          stacked = false
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Query Throughput"
          region = data.aws_region.current.name
          metrics = [
            [
              "${var.project_name}/Application",
              "retail_insights.queries.total",
              "success", "True",
              { stat = "Sum", period = 60, label = "Success" }
            ],
            [
              "...",
              "success", "False",
              { stat = "Sum", period = 60, label = "Errors" }
            ]
          ]
          view   = "timeSeries"
          stacked = true
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "ECS CPU Utilization"
          region = data.aws_region.current.name
          metrics = [
            [
              "AWS/ECS",
              "CPUUtilization",
              "ClusterName", var.ecs_cluster_name,
              "ServiceName", var.ecs_service_name,
              { stat = "Average", period = 60 }
            ]
          ]
          view = "timeSeries"
          annotations = {
            horizontal = [
              {
                value = var.cpu_utilization_threshold
                label = "Alarm Threshold"
                color = "#ff0000"
              }
            ]
          }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "ECS Memory Utilization"
          region = data.aws_region.current.name
          metrics = [
            [
              "AWS/ECS",
              "MemoryUtilization",
              "ClusterName", var.ecs_cluster_name,
              "ServiceName", var.ecs_service_name,
              { stat = "Average", period = 60 }
            ]
          ]
          view = "timeSeries"
          annotations = {
            horizontal = [
              {
                value = var.memory_utilization_threshold
                label = "Alarm Threshold"
                color = "#ff0000"
              }
            ]
          }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "LLM Token Usage"
          region = data.aws_region.current.name
          metrics = [
            [
              "${var.project_name}/Application",
              "retail_insights.llm.tokens",
              "agent", "router",
              { stat = "Sum", period = 300, label = "Router" }
            ],
            [
              "...",
              "agent", "sql_generator",
              { stat = "Sum", period = 300, label = "SQL Generator" }
            ],
            [
              "...",
              "agent", "summarizer",
              { stat = "Sum", period = 300, label = "Summarizer" }
            ]
          ]
          view   = "timeSeries"
          stacked = true
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "Intent Distribution"
          region = data.aws_region.current.name
          metrics = [
            [
              "${var.project_name}/Application",
              "retail_insights.queries.total",
              "intent", "query",
              { stat = "Sum", period = 3600 }
            ],
            [
              "...",
              "intent", "summarize",
              { stat = "Sum", period = 3600 }
            ],
            [
              "...",
              "intent", "chat",
              { stat = "Sum", period = 3600 }
            ]
          ]
          view = "pie"
        }
      }
    ]
  })
}

data "aws_region" "current" {}
