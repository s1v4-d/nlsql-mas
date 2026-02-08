data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = merge(var.tags, {
    Project     = var.project_name
    Environment = var.environment
    Module      = "github-oidc"
    ManagedBy   = "terraform"
  })

  github_oidc_url = "https://token.actions.githubusercontent.com"
  repo_pattern    = "repo:${var.github_org}/${var.github_repo}:*"
  main_pattern    = "repo:${var.github_org}/${var.github_repo}:ref:refs/heads/main"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = local.github_oidc_url
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["ffffffffffffffffffffffffffffffffffffffff"]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-github-oidc"
  })
}

resource "aws_iam_role" "github_actions" {
  name = "github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = local.repo_pattern
        }
      }
    }]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-github-actions-role"
  })
}

resource "aws_iam_role_policy" "ecr_access" {
  count = length(var.ecr_repository_arns) > 0 ? 1 : 0
  name  = "ecr-access"
  role  = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = var.ecr_repository_arns
      }
    ]
  })
}

resource "aws_iam_role_policy" "ecs_deploy" {
  count = length(var.ecs_cluster_arns) > 0 ? 1 : 0
  name  = "ecs-deploy"
  role  = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:DescribeTasks",
          "ecs:ListTasks",
          "ecs:RegisterTaskDefinition",
          "ecs:UpdateService"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = "*"
        Condition = {
          StringLike = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "terraform_state" {
  name = "terraform-state"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:${data.aws_partition.current.partition}:s3:::${var.terraform_state_bucket}",
          "arn:${data.aws_partition.current.partition}:s3:::${var.terraform_state_bucket}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem"
        ]
        Resource = "arn:${data.aws_partition.current.partition}:dynamodb:*:*:table/${var.terraform_lock_table}"
      }
    ]
  })
}

resource "aws_iam_role" "github_actions_terraform" {
  name = "github-actions-terraform"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = local.repo_pattern
        }
      }
    }]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-github-actions-terraform"
  })
}

resource "aws_iam_role_policy_attachment" "terraform_admin" {
  role       = aws_iam_role.github_actions_terraform.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AdministratorAccess"
}

resource "aws_iam_role" "github_actions_terraform_prod" {
  count = var.create_prod_role ? 1 : 0
  name  = "github-actions-terraform-prod"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = local.main_pattern
        }
      }
    }]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-github-actions-terraform-prod"
  })
}

resource "aws_iam_role_policy_attachment" "terraform_prod_admin" {
  count      = var.create_prod_role ? 1 : 0
  role       = aws_iam_role.github_actions_terraform_prod[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AdministratorAccess"
}

resource "aws_iam_role" "github_actions_prod" {
  count = var.create_prod_role ? 1 : 0
  name  = "github-actions-prod-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = local.main_pattern
        }
      }
    }]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-github-actions-prod-role"
  })
}

resource "aws_iam_role_policy" "prod_ecr_access" {
  count = var.create_prod_role && length(var.ecr_repository_arns) > 0 ? 1 : 0
  name  = "ecr-access"
  role  = aws_iam_role.github_actions_prod[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = var.ecr_repository_arns
      }
    ]
  })
}

resource "aws_iam_role_policy" "prod_ecs_deploy" {
  count = var.create_prod_role && length(var.ecs_cluster_arns) > 0 ? 1 : 0
  name  = "ecs-deploy"
  role  = aws_iam_role.github_actions_prod[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:DescribeTasks",
          "ecs:ListTasks",
          "ecs:RegisterTaskDefinition",
          "ecs:UpdateService"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = "*"
        Condition = {
          StringLike = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      }
    ]
  })
}
