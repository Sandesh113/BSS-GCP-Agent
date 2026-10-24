terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 7.0" }
  }
}

variable "project_id" { type = string }
variable "billing_account_id" { type = string }
variable "billing_currency" { type = string }
variable "budget_units" {
  type    = number
  default = 10
}

provider "google" {
  project               = var.project_id
  billing_project       = var.project_id
  user_project_override = true
}

data "google_project" "current" { project_id = var.project_id }

resource "google_project_service" "required" {
  for_each = toset([
    "aiplatform.googleapis.com", "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com", "cloudfunctions.googleapis.com", "cloudresourcemanager.googleapis.com",
    "eventarc.googleapis.com", "logging.googleapis.com",
    "monitoring.googleapis.com", "pubsub.googleapis.com",
    "run.googleapis.com", "storage.googleapis.com", "cloudtrace.googleapis.com",
    "billingbudgets.googleapis.com", "iam.googleapis.com", "secretmanager.googleapis.com"
  ])
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

resource "google_billing_budget" "trial_watch" {
  billing_account = var.billing_account_id
  display_name    = "BSS AI Agent trial usage"
  budget_filter {
    projects               = ["projects/${data.google_project.current.number}"]
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
    calendar_period        = "MONTH"
  }
  amount {
    specified_amount {
      currency_code = var.billing_currency
      units         = tostring(var.budget_units)
    }
  }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.8 }
  threshold_rules { threshold_percent = 1.0 }
  depends_on = [google_project_service.required]
}

output "project_number" { value = data.google_project.current.number }
output "budget_name" { value = google_billing_budget.trial_watch.name }
