# S3 Data Lake Module - Main Configuration
# -----------------------------------------
# S3 buckets for Parquet data, exports, and access logging

data "aws_caller_identity" "current" {}

# Local Values
locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Module      = "s3"
    },
    var.tags
  )
}

# =============================================================================
# KMS Key for S3 Encryption
# =============================================================================

resource "aws_kms_key" "s3" {
  count = var.use_customer_managed_key ? 1 : 0

  description             = "CMK for ${var.project_name} ${var.environment} S3 data lake encryption"
  deletion_window_in_days = var.kms_key_deletion_window
  enable_key_rotation     = true
  multi_region            = false

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowRootFullAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.aws_account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowS3ServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey*"
        ]
        Resource = "*"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-s3-kms-key"
  })
}

resource "aws_kms_alias" "s3" {
  count = var.use_customer_managed_key ? 1 : 0

  name          = "alias/${local.name_prefix}-s3"
  target_key_id = aws_kms_key.s3[0].key_id
}

# =============================================================================
# Access Logs Bucket
# =============================================================================

resource "aws_s3_bucket" "logs" {
  count = var.enable_access_logging ? 1 : 0

  bucket        = "${local.name_prefix}-access-logs-${var.aws_account_id}"
  force_destroy = var.force_destroy

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-access-logs"
  })
}

resource "aws_s3_bucket_ownership_controls" "logs" {
  count = var.enable_access_logging ? 1 : 0

  bucket = aws_s3_bucket.logs[0].id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_acl" "logs" {
  count = var.enable_access_logging ? 1 : 0

  depends_on = [aws_s3_bucket_ownership_controls.logs]

  bucket = aws_s3_bucket.logs[0].id
  acl    = "log-delivery-write"
}

resource "aws_s3_bucket_public_access_block" "logs" {
  count = var.enable_access_logging ? 1 : 0

  bucket = aws_s3_bucket.logs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  count = var.enable_access_logging ? 1 : 0

  bucket = aws_s3_bucket.logs[0].id

  rule {
    id     = "archive-logs"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    expiration {
      days = var.log_retention_days
    }
  }
}

# =============================================================================
# Data Lake Bucket
# =============================================================================

resource "aws_s3_bucket" "data_lake" {
  bucket        = "${local.name_prefix}-data-lake-${var.aws_account_id}"
  force_destroy = var.force_destroy

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-data-lake"
  })
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.use_customer_managed_key ? aws_kms_key.s3[0].arn : null
      sse_algorithm     = var.use_customer_managed_key ? "aws:kms" : "AES256"
    }
    bucket_key_enabled = var.use_customer_managed_key
  }
}

resource "aws_s3_bucket_logging" "data_lake" {
  count = var.enable_access_logging ? 1 : 0

  bucket = aws_s3_bucket.data_lake.id

  target_bucket = aws_s3_bucket.logs[0].id
  target_prefix = "s3-access-logs/${aws_s3_bucket.data_lake.id}/"
}

# Intelligent Tiering Configuration
resource "aws_s3_bucket_intelligent_tiering_configuration" "data_lake" {
  count = var.enable_intelligent_tiering ? 1 : 0

  bucket = aws_s3_bucket.data_lake.id
  name   = "analytics-tiering"

  filter {
    prefix = "processed/"
  }

  tiering {
    access_tier = "ARCHIVE_ACCESS"
    days        = var.archive_access_days
  }

  tiering {
    access_tier = "DEEP_ARCHIVE_ACCESS"
    days        = var.deep_archive_access_days
  }
}

# Lifecycle Rules
resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  # Move processed data to Intelligent Tiering
  rule {
    id     = "intelligent-tiering-processed"
    status = var.enable_intelligent_tiering ? "Enabled" : "Disabled"

    filter {
      prefix = "processed/"
    }

    transition {
      days          = 0
      storage_class = "INTELLIGENT_TIERING"
    }
  }

  # Expire exports after configured days
  rule {
    id     = "expire-exports"
    status = "Enabled"

    filter {
      prefix = "exports/"
    }

    expiration {
      days = var.export_expiration_days
    }
  }

  # Clean up incomplete multipart uploads
  rule {
    id     = "cleanup-incomplete-uploads"
    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 3
    }
  }

  # Archive raw data
  rule {
    id     = "archive-raw-data"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    transition {
      days          = 7
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 30
      storage_class = "GLACIER"
    }
  }
}

# =============================================================================
# Bucket Policy
# =============================================================================

resource "aws_s3_bucket_policy" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid       = "DenyInsecureTransport"
          Effect    = "Deny"
          Principal = "*"
          Action    = "s3:*"
          Resource = [
            aws_s3_bucket.data_lake.arn,
            "${aws_s3_bucket.data_lake.arn}/*"
          ]
          Condition = {
            Bool = {
              "aws:SecureTransport" = "false"
            }
          }
        }
      ],
      var.restrict_to_vpc_endpoint && var.vpc_endpoint_id != null ? [
        {
          Sid       = "DenyNonVPCEndpointAccess"
          Effect    = "Deny"
          Principal = "*"
          Action    = "s3:*"
          Resource = [
            aws_s3_bucket.data_lake.arn,
            "${aws_s3_bucket.data_lake.arn}/*"
          ]
          Condition = {
            StringNotEquals = {
              "aws:SourceVpce" = var.vpc_endpoint_id
            }
          }
        }
      ] : []
    )
  })
}

# =============================================================================
# IAM Policies for Access
# =============================================================================

resource "aws_iam_policy" "s3_read" {
  name        = "${local.name_prefix}-s3-read"
  description = "Read access to ${var.project_name} data lake"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Effect = "Allow"
          Action = [
            "s3:GetObject",
            "s3:GetObjectVersion",
            "s3:ListBucket"
          ]
          Resource = [
            aws_s3_bucket.data_lake.arn,
            "${aws_s3_bucket.data_lake.arn}/processed/*",
            "${aws_s3_bucket.data_lake.arn}/metadata/*"
          ]
        }
      ],
      var.use_customer_managed_key ? [
        {
          Effect = "Allow"
          Action = [
            "kms:Decrypt",
            "kms:GenerateDataKey"
          ]
          Resource = [aws_kms_key.s3[0].arn]
        }
      ] : []
    )
  })

  tags = local.common_tags
}

resource "aws_iam_policy" "s3_write" {
  name        = "${local.name_prefix}-s3-write"
  description = "Write access to ${var.project_name} exports"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Effect = "Allow"
          Action = [
            "s3:PutObject",
            "s3:DeleteObject"
          ]
          Resource = [
            "${aws_s3_bucket.data_lake.arn}/exports/*"
          ]
        }
      ],
      var.use_customer_managed_key ? [
        {
          Effect = "Allow"
          Action = [
            "kms:Encrypt",
            "kms:GenerateDataKey"
          ]
          Resource = [aws_kms_key.s3[0].arn]
        }
      ] : []
    )
  })

  tags = local.common_tags
}
