terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Partial backend configuration.
  # Supply the bucket name at init time:
  #   Local:  terraform init -backend-config="bucket=YOUR-STATE-BUCKET"
  #   CI:     terraform init -backend-config="bucket=${{ secrets.TF_STATE_BUCKET }}"
  backend "s3" {
    key    = "lab4/terraform.tfstate"
    region = "eu-north-1"
  }
}

provider "aws" {
  region = var.aws_region
}

# ── S3 Bucket ──────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "app_storage" {
  bucket = var.bucket_name

  tags = {
    Name        = var.bucket_name
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

# ── Public Access Block ────────────────────────────────────────────────────────

resource "aws_s3_bucket_public_access_block" "app_storage" {
  bucket = aws_s3_bucket.app_storage.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── Versioning ─────────────────────────────────────────────────────────────────

resource "aws_s3_bucket_versioning" "app_storage" {
  bucket = aws_s3_bucket.app_storage.id

  versioning_configuration {
    status = "Disabled"
  }
}
