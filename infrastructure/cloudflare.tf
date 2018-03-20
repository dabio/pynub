variable "cloudflare_email" {}
variable "cloudflare_token" {}

provider "cloudflare" {
  email = "${var.cloudflare_email}"
  token = "${var.cloudflare_token}"
}

resource "cloudflare_record" "pinub_com" {
  domain  = "${var.domain}"
  name    = "pinub.com"
  value   = "${heroku_domain.pinub_com.cname}"
  type    = "CNAME"
  proxied = true
}

resource "cloudflare_record" "www_pinub_com" {
  domain  = "${var.domain}"
  name    = "www"
  value   = "${heroku_domain.www_pinub_com.cname}"
  type    = "CNAME"
  proxied = true
}
