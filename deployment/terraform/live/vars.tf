# Notes
#
# To add a CIDR block to your VPC, the following rules apply:
# The CIDR block must not be the same or larger than the CIDR range of a route
# in any of the VPC route tables. For example, if you have a route with a
# destination of 10.0.0.0/24 to a virtual private gateway, you cannot associate
# a CIDR block of the same range or larger. However, you can associate a CIDR
# block of 10.0.0.0/25 or smaller.
# https://docs.aws.amazon.com/AmazonVPC/latest/UserGuide/VPC_Subnets.html#vpc-subnet-basics
#
# Email addresses for Django settings
# to successfully send email these addresses must be verified for Amazon SES
# and the AWS account should be out of the sandbox
# http://docs.aws.amazon.com/ses/latest/DeveloperGuide/verify-addresses-and-domains.html

variable "region" {
  description = "The AWS region to use"
  default     = "us-east-1"
}

variable "availability_zone_a" {
  default = "us-east-1a"
}

variable "availability_zone_b" {
  default = "us-east-1b"
}

variable "vpc_cidr_block" {
  type    = "string"
  default = "10.0.0.0/24"
}

variable "public_cidr_block" {
  type    = "string"
  default = "10.0.0.128/25"
}

variable "private_cidr_block_a" {
  type    = "string"
  default = "10.0.0.64/26"
}

variable "private_cidr_block_b" {
  type    = "string"
  default = "10.0.0.0/26"
}

variable "tags" {
  type        = "map"
  description = "Resource tags"
  default     = {}
}

variable "rds_snapshot_id" {
  description = "Name of the DB snapshot that's used to restore the DB instance"
  default     = ""
}

variable "rds_master_user_password" {
  description = "Password for the master DB user"
  default     = ""  # will be autogenerated if left blank
}

variable "app_server_instance_type" {
  default = "m3.medium"
}

variable "app_server_key_pair_name" {
  description = "Name of the key pair to use for the app server instance"
}

variable "app_server_ssh_users" {
  type        = "list"
  description = "Github usernames to be allowed SSH access to the app server instance"
  default     = []
}

variable "git_commit" {
  description = "Github repo code commit to use for deployment"
  default     = ""
}

variable "django_admin_password" {
  description = "Password for Django superuser"
  default     = ""  # will be autogenerated if left blank
}

variable "django_default_from_email" {
  description = "Default email address to use for various automated correspondence from the site manager(s)"
  default     = "webmaster@localhost"
}

variable "django_server_email" {
  description = "Email address that error messages come from"
  default     = "root@localhost"
}

variable "django_admin_email" {
  description = "Email address for code error notifications (full exception information)"
  default     = ""
}

variable "site_name" {
  description = "Name of the site (cannot contain apostrophes)"
  default     = "Refinery Platform"
}

variable "site_domain" {
  description = "Host name of the site (for example: www.example.org)"
}

variable "ssl_certificate_id" {
  description = "ARN of an SSL certificate you have uploaded to AWS IAM"
  default     = ""
}

variable "django_email_subject_prefix" {
  description = "Subject-line prefix for email messages"
  default     = "[Refinery] "
}

variable "refinery_banner" {
  description = "Message to display near the top of every page (HTML allowed)"
  default     = ""
}

variable "refinery_banner_anonymous_only" {
  description = "Whether to display refinery_banner to anonymous users only or everyone"
  default = "false"
}

variable "refinery_custom_navbar_item" {
  description = "HTML-safe item to be displayed to the right of the `About` link in the navbar"
  default     = "<a href=\"http://example.org/\">Sample Entry</a>"
}

variable "refinery_welcome_email_subject" {
  description = "Subject of email message sent to new users after their account is activated"
  default     = "Welcome to Refinery"
}

variable "refinery_welcome_email_message" {
  description = "Email message sent to new users after their account is activated"
  default     = "Please fill out your user profile"
}

variable "refinery_google_analytics_id" {
  description = "Google Analytics ID for the site"
  default     = ""
}

variable "refinery_google_recaptcha_site_key" {
  description = "Google ReCAPTCHA site key"
  default     = ""
}

variable "refinery_google_recaptcha_secret_key" {
  description = "Google ReCAPTCHA secret key"
  default     = ""
}

variable "refinery_s3_user_data" {
  description = "Whether or not to use S3 as user data file storage backend"
  default     = "false"
}
variable "refinery_user_files_columns" {
  default = "name,filetype,sample_name,organism,technology,genotype,cell_type,antibody,experimenter,date_submitted"
}

variable "data_volume_size" {
  description = "Size of the EBS data volume in GB"
  default     = 500
}

variable "data_volume_type" {
  description = "Type of the EBS data volume"
  default     = "st1"
}

variable "data_volume_snapshot_id" {
  description = "A snapshot to base the EBS data volume off of"
  default     = ""
}
