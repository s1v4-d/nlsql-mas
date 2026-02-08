# Backend Configuration for Production Environment
# -------------------------------------------------
# S3 backend for remote state storage

terraform {
  backend "s3" {
    bucket         = "nlsql-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "nlsql-terraform-locks"
  }
}
