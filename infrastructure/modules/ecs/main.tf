data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    Module      = "ecs"
    ManagedBy   = "terraform"
  })

  # Capacity provider weights based on environment
  fargate_weight = var.environment == "prod" ? var.fargate_weight : 20
  spot_weight    = var.environment == "prod" ? var.fargate_spot_weight : 80
}

resource "aws_ecr_repository" "services" {
  for_each = var.services

  name                 = "${var.project_name}-${each.key}"
  image_tag_mutability = var.environment == "prod" ? "IMMUTABLE" : "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = var.kms_key_arn != null ? "KMS" : "AES256"
    kms_key         = var.kms_key_arn
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-${each.key}-ecr"
    Service = each.key
  })
}

# ECR Lifecycle Policy
resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 production images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["prod-", "v", "release-"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep last 5 dev images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["dev-", "staging-", "latest"]
          countType     = "imageCountMoreThan"
          countNumber   = 5
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 3
        description  = "Delete untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

resource "aws_ecs_cluster" "main" {
  name = local.name_prefix

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  configuration {
    execute_command_configuration {
      logging = "OVERRIDE"

      log_configuration {
        cloud_watch_log_group_name = aws_cloudwatch_log_group.ecs_exec.name
      }
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cluster"
  })
}

# Capacity Providers
resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = var.use_fargate_spot ? ["FARGATE", "FARGATE_SPOT"] : ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = local.fargate_weight
    base              = var.fargate_base
  }

  dynamic "default_capacity_provider_strategy" {
    for_each = var.use_fargate_spot ? [1] : []
    content {
      capacity_provider = "FARGATE_SPOT"
      weight            = local.spot_weight
    }
  }
}

# Service Discovery Namespace (for Service Connect)
resource "aws_service_discovery_http_namespace" "main" {
  name        = var.project_name
  description = "Service Connect namespace for ${var.project_name}"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-namespace"
  })
}

resource "aws_cloudwatch_log_group" "ecs_exec" {
  name              = "/ecs/${local.name_prefix}/exec"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-exec-logs"
  })
}

resource "aws_cloudwatch_log_group" "services" {
  for_each = var.services

  name              = "/ecs/${local.name_prefix}/${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-${each.key}-logs"
    Service = each.key
  })
}

resource "aws_iam_role" "task_execution" {
  name = "${local.name_prefix}-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-task-execution-role"
  })
}

resource "aws_iam_role_policy_attachment" "task_execution_base" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional permissions for Secrets Manager
resource "aws_iam_role_policy" "task_execution_secrets" {
  name = "secrets-access"
  role = aws_iam_role.task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          "arn:${data.aws_partition.current.partition}:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameters",
          "ssm:GetParameter"
        ]
        Resource = [
          "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = var.kms_key_arn != null ? [var.kms_key_arn] : ["*"]
        Condition = var.kms_key_arn == null ? {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.${var.aws_region}.amazonaws.com"
          }
        } : null
      }
    ]
  })
}

resource "aws_iam_role" "task" {
  name = "${local.name_prefix}-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-task-role"
  })
}

# S3 Access for DuckDB + Parquet
resource "aws_iam_role_policy" "task_s3" {
  count = var.s3_data_bucket_arn != null ? 1 : 0
  name  = "s3-data-access"
  role  = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          var.s3_data_bucket_arn,
          "${var.s3_data_bucket_arn}/*"
        ]
      }
    ]
  })
}

# CloudWatch Logs access from application
resource "aws_iam_role_policy" "task_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/ecs/${local.name_prefix}/*"
        ]
      }
    ]
  })
}

# SSM for ECS Exec
resource "aws_iam_role_policy" "task_ssm" {
  count = var.enable_execute_command ? 1 : 0
  name  = "ssm-exec"
  role  = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lb" "main" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = var.environment == "prod"
  enable_http2               = true
  idle_timeout               = var.alb_idle_timeout

  dynamic "access_logs" {
    for_each = var.enable_alb_access_logs && var.alb_access_logs_bucket != null ? [1] : []
    content {
      bucket  = var.alb_access_logs_bucket
      prefix  = "alb-logs/${local.name_prefix}"
      enabled = true
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-alb"
  })
}

# HTTP Listener (redirect to HTTPS or serve directly)
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = var.enable_https ? "redirect" : "forward"

    dynamic "redirect" {
      for_each = var.enable_https ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }

    # Forward to API when HTTPS is disabled (dev environment)
    target_group_arn = var.enable_https ? null : aws_lb_target_group.services["api"].arn
  }
}

# HTTPS Listener (only when certificate is provided)
resource "aws_lb_listener" "https" {
  count = var.enable_https ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "application/json"
      message_body = jsonencode({ error = "Not Found" })
      status_code  = "404"
    }
  }
}

# Target Groups
resource "aws_lb_target_group" "services" {
  for_each = var.services

  name        = "${local.name_prefix}-${each.key}"
  port        = each.value.container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    path                = each.value.health_check_path
    matcher             = "200"
    protocol            = "HTTP"
  }

  # Stickiness for Streamlit sessions
  stickiness {
    type            = "lb_cookie"
    cookie_duration = each.key == "streamlit" ? 86400 : 3600
    enabled         = each.key == "streamlit"
  }

  # Deregistration delay (faster in dev)
  deregistration_delay = var.environment == "prod" ? 30 : 10

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-${each.key}-tg"
    Service = each.key
  })

  lifecycle {
    create_before_destroy = true
  }
}

# Listener Rules for HTTP (dev mode without HTTPS)
resource "aws_lb_listener_rule" "http_api" {
  count = var.enable_https ? 0 : 1

  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services["api"].arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/health", "/docs", "/openapi.json", "/redoc"]
    }
  }
}

resource "aws_lb_listener_rule" "http_streamlit" {
  count = var.enable_https ? 0 : (contains(keys(var.services), "streamlit") ? 1 : 0)

  listener_arn = aws_lb_listener.http.arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services["streamlit"].arn
  }

  condition {
    path_pattern {
      values = ["/*"]
    }
  }
}

# Listener Rules for HTTPS (production mode)
resource "aws_lb_listener_rule" "https_api" {
  count = var.enable_https ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services["api"].arn
  }

  condition {
    path_pattern {
      values = ["/api/*", "/health", "/docs", "/openapi.json", "/redoc"]
    }
  }
}

resource "aws_lb_listener_rule" "https_streamlit" {
  count = var.enable_https && contains(keys(var.services), "streamlit") ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.services["streamlit"].arn
  }

  condition {
    path_pattern {
      values = ["/*"]
    }
  }
}

resource "aws_ecs_task_definition" "services" {
  for_each = var.services

  family                   = "${local.name_prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = each.key
      image     = lookup(var.container_images, each.key, "${aws_ecr_repository.services[each.key].repository_url}:latest")
      essential = true

      portMappings = [{
        name          = each.key
        containerPort = each.value.container_port
        hostPort      = each.value.container_port
        protocol      = "tcp"
        appProtocol   = "http"
      }]

      environment = concat(
        [
          { name = "ENVIRONMENT", value = var.environment },
          { name = "AWS_REGION", value = var.aws_region },
          { name = "LOG_LEVEL", value = var.environment == "prod" ? "INFO" : "DEBUG" },
          { name = "PORT", value = tostring(each.value.container_port) }
        ],
        var.create_app_secrets ? [
          { name = "AWS_SECRETS_MANAGER_SECRET_ID", value = aws_secretsmanager_secret.app[0].name }
        ] : [],
        [for k, v in each.value.environment_variables : { name = k, value = v }]
      )

      secrets = concat(
        var.create_app_secrets ? [
          { name = "OPENAI_API_KEY", valueFrom = "${aws_secretsmanager_secret.app[0].arn}:OPENAI_API_KEY::" },
          { name = "API_KEY", valueFrom = "${aws_secretsmanager_secret.app[0].arn}:API_KEY::" },
          { name = "ADMIN_API_KEY", valueFrom = "${aws_secretsmanager_secret.app[0].arn}:ADMIN_API_KEY::" }
        ] : [],
        [for k, v in each.value.secrets : { name = k, valueFrom = v }]
      )

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${each.value.container_port}${each.value.health_check_path} || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.services[each.key].name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      ulimits = [{
        name      = "nofile"
        softLimit = 65536
        hardLimit = 65536
      }]

      linuxParameters = {
        initProcessEnabled = true
      }
    }
  ])

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-${each.key}-task-def"
    Service = each.key
  })
}

resource "aws_ecs_service" "services" {
  for_each = var.services

  name                   = each.key
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.services[each.key].arn
  desired_count          = each.value.desired_count
  launch_type            = null # Use capacity provider strategy
  enable_execute_command = var.enable_execute_command
  propagate_tags         = "SERVICE"

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = local.fargate_weight
    base              = var.fargate_base
  }

  dynamic "capacity_provider_strategy" {
    for_each = var.use_fargate_spot ? [1] : []
    content {
      capacity_provider = "FARGATE_SPOT"
      weight            = local.spot_weight
    }
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.ecs_tasks_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.services[each.key].arn
    container_name   = each.key
    container_port   = each.value.container_port
  }

  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.main.arn

    service {
      port_name      = each.key
      discovery_name = each.key

      client_alias {
        port     = each.value.container_port
        dns_name = each.key
      }
    }
  }

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = var.environment == "prod"
  }

  wait_for_steady_state = var.environment == "prod"

  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-${each.key}-service"
    Service = each.key
  })

  depends_on = [aws_lb_listener.http, aws_lb_listener.https]
}

resource "aws_appautoscaling_target" "services" {
  for_each = var.services

  max_capacity       = each.value.max_capacity
  min_capacity       = each.value.min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.services[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# CPU Target Tracking
resource "aws_appautoscaling_policy" "cpu" {
  for_each = var.services

  name               = "${each.key}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.services[each.key].resource_id
  scalable_dimension = aws_appautoscaling_target.services[each.key].scalable_dimension
  service_namespace  = aws_appautoscaling_target.services[each.key].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = var.cpu_target_value
    scale_in_cooldown  = var.scale_in_cooldown
    scale_out_cooldown = var.scale_out_cooldown
  }
}

# Memory Target Tracking
resource "aws_appautoscaling_policy" "memory" {
  for_each = var.services

  name               = "${each.key}-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.services[each.key].resource_id
  scalable_dimension = aws_appautoscaling_target.services[each.key].scalable_dimension
  service_namespace  = aws_appautoscaling_target.services[each.key].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value       = var.memory_target_value
    scale_in_cooldown  = var.scale_in_cooldown
    scale_out_cooldown = var.scale_out_cooldown
  }
}

# Application Secrets
resource "aws_secretsmanager_secret" "app" {
  count = var.create_app_secrets ? 1 : 0

  name                    = "${var.project_name}/${var.environment}/app"
  description             = "Application secrets for ${var.project_name} ${var.environment}"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = var.environment == "prod" ? 30 : 0

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-app-secrets"
  })
}

resource "aws_secretsmanager_secret_version" "app" {
  count = var.create_app_secrets ? 1 : 0

  secret_id = aws_secretsmanager_secret.app[0].id
  secret_string = jsonencode({
    OPENAI_API_KEY = var.openai_api_key
    API_KEY        = var.api_key
    ADMIN_API_KEY  = var.admin_api_key
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
