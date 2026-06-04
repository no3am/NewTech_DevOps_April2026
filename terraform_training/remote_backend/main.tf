terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "devopsclassapril26"
    key    = "terraform.tfstate"
    region = "eu-central-1"
  }
}

resource "aws_instance" "web" {
  ami           = "ami-036bdae36143a955f"
  instance_type = var.instance_type

  tags = {
    Name = "terraform-training"
  }
}