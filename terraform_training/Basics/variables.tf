variable "region" {
  type        = string
  description = "The region to deploy the resources"
  #default     = "us-east-1"
}

variable "ami" {
  type        = string
  description = "The AMI to deploy the resources"
  #default     = "ami-036bdae36143a955f"
}

variable "instance_type" {
  type        = string
  description = "The instance type to deploy the resources"
  #default     = "t3.micro"
}