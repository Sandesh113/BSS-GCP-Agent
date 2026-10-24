terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 7.0" }
  }
}

variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "europe-west2"
}
variable "image" { type = string }
variable "operator_email" { type = string }
variable "gmail_oauth_client_id" {
  type    = string
  default = ""
}
variable "gmail_sender_email" {
  type    = string
  default = ""
}
variable "results_bucket" { type = string }
variable "requests_topic" { type = string }
variable "model_name" {
  type    = string
  default = "gemini-3.5-flash"
}
variable "model_region" {
  type    = string
  default = "eu"
}
variable "model_api_endpoint" {
  type    = string
  default = "https://aiplatform.eu.rep.googleapis.com"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "gmail" {
  project            = var.project_id
  service            = "gmail.googleapis.com"
  disable_on_destroy = false
}

locals { labels = { app = "bss-ai-agent", environment = "demo", managed_by = "terraform" } }

data "google_project" "current" { project_id = var.project_id }

locals {
  build_account = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_artifact_registry_repository" "ui" {
  project       = var.project_id
  location      = var.region
  repository_id = "bss-ui"
  description   = "BSS catalogue and CPQ demo images"
  format        = "DOCKER"
  labels        = local.labels
}

resource "google_storage_bucket_iam_member" "build_source_reader" {
  bucket = "${var.project_id}_cloudbuild"
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${local.build_account}"
}

resource "google_artifact_registry_repository_iam_member" "build_image_writer" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.ui.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${local.build_account}"
}

resource "google_project_iam_member" "build_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${local.build_account}"
}

resource "google_storage_bucket" "state" {
  name                        = "${var.project_id}-bss-state"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.labels
  versioning { enabled = true }
}

resource "google_service_account" "ui" {
  project      = var.project_id
  account_id   = "bss-ui"
  display_name = "BSS catalogue and CPQ Cloud Run runtime"
}

resource "google_project_iam_custom_role" "catalogue_predictor" {
  project     = var.project_id
  role_id     = "bssCataloguePredictor"
  title       = "BSS catalogue Gemini predictor"
  description = "Only the Vertex permission needed to interpret product-manager answers"
  permissions = ["aiplatform.endpoints.predict"]
  stage       = "GA"
}

resource "google_project_iam_member" "ui_model_predict" {
  project = var.project_id
  role    = google_project_iam_custom_role.catalogue_predictor.id
  member  = "serviceAccount:${google_service_account.ui.email}"
}

resource "google_storage_bucket_iam_member" "state_editor" {
  bucket = google_storage_bucket.state.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ui.email}"
}

resource "google_storage_bucket_iam_member" "result_reader" {
  bucket = var.results_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.ui.email}"
}

resource "google_pubsub_topic_iam_member" "request_publisher" {
  project = var.project_id
  topic   = var.requests_topic
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.ui.email}"
}

resource "google_cloud_run_v2_service" "ui" {
  project             = var.project_id
  name                = "bss-catalogue-cpq"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  labels              = local.labels

  template {
    service_account                  = google_service_account.ui.email
    max_instance_request_concurrency = 1
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    containers {
      image = var.image
      ports { container_port = 8080 }
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
      env {
        name  = "STATE_BUCKET"
        value = google_storage_bucket.state.name
      }
      env {
        name  = "RESULT_BUCKET"
        value = var.results_bucket
      }
      env {
        name  = "REQUESTS_TOPIC"
        value = var.requests_topic
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "MODEL_NAME"
        value = var.model_name
      }
      env {
        name  = "MODEL_REGION"
        value = var.model_region
      }
      env {
        name  = "MODEL_API_ENDPOINT"
        value = var.model_api_endpoint
      }
      env {
        name  = "MAIL_PROVIDER"
        value = "gmail"
      }
      env {
        name  = "GMAIL_OAUTH_CLIENT_ID"
        value = var.gmail_oauth_client_id
      }
      env {
        name  = "GMAIL_SENDER_EMAIL"
        value = var.gmail_sender_email
      }
    }
  }
  depends_on = [google_storage_bucket_iam_member.state_editor, google_project_iam_member.ui_model_predict]
}

resource "google_cloud_run_v2_service_iam_member" "operator_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.ui.name
  role     = "roles/run.invoker"
  member   = "user:${var.operator_email}"
}

output "state_bucket" { value = google_storage_bucket.state.name }
output "service_url" { value = google_cloud_run_v2_service.ui.uri }
output "service_account" { value = google_service_account.ui.email }
output "repository" { value = google_artifact_registry_repository.ui.id }
