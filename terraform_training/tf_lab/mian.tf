provider "aws" {
  region = "eu-central-1"
}

resource "aws_security_group" "allow_ssh" {
  name = "allow_ssh"
  
}

resource "aws_security_group_rule" "ssh_in" {
  type              = "ingress"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.allow_ssh.id
}

resource "aws_security_group_rule" "http_in" {
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.allow_ssh.id
}


resource "aws_key_pair" "my_key" {
  key_name   = "terraform-training-key"
  public_key = file("~/.ssh/id_ed25519.pub")
}

# -------------------------------------------------------
# OPTION: Let Terraform generate the key pair (like the EC2 wizard)
# Uncomment the block below and remove the aws_key_pair above when ready
# Also requires adding "tls" and "local" to required_providers
# -------------------------------------------------------
# resource "tls_private_key" "my_key" {
#   algorithm = "RSA"
#   rsa_bits  = 4096
# }
#
# resource "aws_key_pair" "my_key" {
#   key_name   = "terraform-training-key"
#   public_key = tls_private_key.my_key.public_key_openssh
# }
#
# resource "local_file" "private_key" {
#   content         = tls_private_key.my_key.private_key_pem
#   filename        = "terraform-training-key.pem"
#   file_permission = "0400"
# }
# -------------------------------------------------------

resource "aws_instance" "web" {
  ami           = "ami-036bdae36143a955f"
  instance_type = "t3.micro"
  region        = "eu-central-1"
  #key_name      = aws_key_pair.my_key.key_name

  security_groups = [aws_security_group.allow_ssh.name]

  tags = {
    Name = "terraform-training"
  }
}

resource "aws_instance" "web_2" {
  ami           = var.ami
  instance_type = var.instance_type
  region        = var.region
  #key_name      = aws_key_pair.my_key.key_name

  security_groups = [aws_security_group.allow_ssh.name]

  tags = {
    Name = "terraform-training-2"
  }
}