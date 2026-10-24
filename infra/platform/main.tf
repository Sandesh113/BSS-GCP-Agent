terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 7.0" }
    random = { source = "hashicorp/random", version = "~> 3.0" }
  }
}

variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "europe-west2"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals { labels = { app = "bss-ai-agent", environment = "demo", managed_by = "terraform" } }

resource "random_id" "suffix" { byte_length = 4 }

resource "google_storage_bucket" "artifacts" {
  name                        = "${var.project_id}-bss-artifacts-${random_id.suffix.hex}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels
  versioning { enabled = true }
}

resource "google_storage_bucket" "results" {
  name                        = "${var.project_id}-bss-results-${random_id.suffix.hex}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels
  versioning { enabled = true }
}

resource "google_pubsub_topic" "requests" {
  name   = "bss-customer-requests"
  labels = local.labels
}
resource "google_pubsub_topic" "status" {
  name   = "bss-quote-status"
  labels = local.labels
}

resource "google_pubsub_subscription" "status_audit" {
  name                       = "bss-quote-status-audit"
  topic                      = google_pubsub_topic.status.id
  ack_deadline_seconds       = 20
  message_retention_duration = "86400s"
  labels                     = local.labels
}

resource "google_service_account" "function" {
  account_id   = "bss-quote-function"
  display_name = "BSS quote function runtime"
}

resource "google_service_account" "agent" {
  account_id   = "bss-quote-agent"
  display_name = "BSS quote Agent Runtime"
}

resource "google_service_account" "trigger" {
  account_id   = "bss-request-trigger"
  display_name = "BSS Pub/Sub Eventarc trigger"
}

resource "google_storage_bucket_iam_member" "result_creator" {
  bucket = google_storage_bucket.results.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.function.email}"
}

resource "google_storage_bucket_iam_member" "agent_artifact_viewer" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_storage_bucket_iam_member" "result_viewer" {
  bucket = google_storage_bucket.results.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.function.email}"
}

resource "google_pubsub_topic_iam_member" "status_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.status.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.function.email}"
}

resource "google_project_iam_member" "function_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.function.email}"
}

resource "google_project_iam_member" "agent_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_project_iam_member" "function_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.function.email}"
}

resource "google_project_iam_member" "agent_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_project_iam_member" "trigger_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.trigger.email}"
}

resource "google_project_iam_member" "trigger_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.trigger.email}"
}

output "artifacts_bucket" { value = google_storage_bucket.artifacts.name }
output "results_bucket" { value = google_storage_bucket.results.name }
output "requests_topic" { value = google_pubsub_topic.requests.id }
output "status_topic" { value = google_pubsub_topic.status.id }
output "function_sa" { value = google_service_account.function.email }
output "agent_sa" { value = google_service_account.agent.email }
output "trigger_sa" { value = google_service_account.trigger.email }
