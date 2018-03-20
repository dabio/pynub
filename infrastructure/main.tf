terraform {
  backend "s3" {
    encrypt = true
    bucket  = "tf-infra"
    key     = "pynub-heroku.tfstate"
    region  = "eu-central-1"
  }
}

variable "domain" {
  type    = "string"
  default = "pinub.com"
}
