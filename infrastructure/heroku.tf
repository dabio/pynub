variable "heroku_email" {}
variable "heroku_api_key" {}

provider "heroku" {
  email   = "${var.heroku_email}"
  api_key = "${var.heroku_api_key}"
}

resource "heroku_app" "pinub" {
  name   = "pynub"
  region = "eu"
  stack  = "heroku-16"
}

resource "heroku_domain" "pinub_com" {
  app      = "${heroku_app.pinub.name}"
  hostname = "${var.domain}"
}

resource "heroku_domain" "www_pinub_com" {
  app      = "${heroku_app.pinub.name}"
  hostname = "www.${var.domain}"
}
