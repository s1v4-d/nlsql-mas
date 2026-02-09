# Backend Configuration

# S3 backend with native state locking (Terraform 1.10+)

terraform {
  backend "s3" {
    bucket       = "nlsql-terraform-state"
    key          = "dev/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
