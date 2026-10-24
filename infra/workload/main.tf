terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google  = { source = "hashicorp/google", version = "~> 7.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "europe-west2"
}
variable "artifacts_bucket" { type = string }
variable "results_bucket" { type = string }
variable "state_bucket" { type = string }
variable "requests_topic" { type = string }
variable "status_topic" { type = string }
variable "function_sa" { type = string }
variable "agent_sa" { type = string }
variable "trigger_sa" { type = string }
variable "model_provider" {
  type    = string
  default = "vertexai"
}
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
  default = "aiplatform.eu.rep.googleapis.com"
}
variable "agent_revision" { type = string }
variable "model_api_key_secret" {
  type        = string
  default     = ""
  description = "Optional Secret Manager secret ID containing the provider API key"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals { labels = { app = "bss-ai-agent", environment = "demo", managed_by = "terraform" } }

data "google_project" "current" { project_id = var.project_id }

locals {
  build_account = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

resource "google_artifact_registry_repository" "functions" {
  project       = var.project_id
  location      = var.region
  repository_id = "bss-functions"
  description   = "BSS event function images"
  format        = "DOCKER"
  labels        = local.labels
}

resource "google_artifact_registry_repository_iam_member" "function_build_writer" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.functions.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${local.build_account}"
}

resource "google_storage_bucket_iam_member" "function_build_source_reader" {
  bucket = var.artifacts_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${local.build_account}"
}

resource "google_storage_bucket_iam_member" "function_staged_source_reader" {
  bucket = "gcf-v2-sources-${data.google_project.current.number}-${var.region}"
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${local.build_account}"
}

data "archive_file" "function_source" {
  type        = "zip"
  output_path = "${path.module}/function-source.zip"
  source {
    content  = file("${path.module}/../../function/main.py")
    filename = "main.py"
  }
  source {
    content  = file("${path.module}/../../function/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("${path.module}/../../bss_core.py")
    filename = "bss_core.py"
  }
  source {
    content  = file("${path.module}/../../catalogue_core.py")
    filename = "catalogue_core.py"
  }
  source {
    content  = file("${path.module}/../../product_constraints.py")
    filename = "product_constraints.py"
  }
  source {
    content  = file("${path.module}/../../cpq_core.py")
    filename = "cpq_core.py"
  }
  source {
    content  = file("${path.module}/../../cpq_policy.json")
    filename = "cpq_policy.json"
  }
  source {
    content  = file("${path.module}/../../customer_core.py")
    filename = "customer_core.py"
  }
  source {
    content  = file("${path.module}/../../business_rules.py")
    filename = "business_rules.py"
  }
  source {
    content  = file("${path.module}/../../business_rules.json")
    filename = "business_rules.json"
  }
  source {
    content  = file("${path.module}/../../catalogue.json")
    filename = "catalogue.json"
  }
}

resource "google_storage_bucket_object" "function_source" {
  name   = "function/source-${data.archive_file.function_source.output_md5}.zip"
  bucket = var.artifacts_bucket
  source = data.archive_file.function_source.output_path
}

resource "google_vertex_ai_reasoning_engine" "agent" {
  project      = var.project_id
  region       = var.region
  display_name = "BSS LangChain quote agent ${substr(var.agent_revision, 0, 12)}"
  description  = "Catalogue selection proposal; deterministic validation runs in Cloud Run"
  labels       = local.labels
  spec {
    agent_framework = "langchain"
    service_account = var.agent_sa
    class_methods = jsonencode([{
      name        = "query"
      api_mode    = ""
      description = "Propose active product offering IDs for a customer request"
      parameters = {
        type       = "object"
        properties = { input = { type = "string" } }
        required   = ["input"]
      }
    }])
    package_spec {
      python_version        = "3.12"
      pickle_object_gcs_uri = "gs://${var.artifacts_bucket}/agent/${var.agent_revision}/agent.pkl"
      requirements_gcs_uri  = "gs://${var.artifacts_bucket}/agent/${var.agent_revision}/requirements.txt"
    }
    deployment_spec {
      min_instances = 0
      max_instances = 2
      env {
        name  = "MODEL_PROVIDER"
        value = var.model_provider
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
      dynamic "secret_env" {
        for_each = var.model_api_key_secret == "" ? [] : [var.model_api_key_secret]
        content {
          name = "OPENAI_API_KEY"
          secret_ref {
            secret  = secret_env.value
            version = "latest"
          }
        }
      }
    }
  }
  depends_on = [google_secret_manager_secret_iam_member.model_key_access]
}

resource "google_secret_manager_secret_iam_member" "model_key_access" {
  count     = var.model_api_key_secret == "" ? 0 : 1
  project   = var.project_id
  secret_id = var.model_api_key_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.agent_sa}"
}

resource "google_storage_bucket_iam_member" "function_state_reader" {
  bucket = var.state_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.function_sa}"
}

resource "google_cloudfunctions2_function" "request_processor" {
  name        = "bss-quote-processor"
  project     = var.project_id
  location    = var.region
  description = "Validate and price customer requests from Pub/Sub"
  labels      = local.labels
  build_config {
    runtime           = "python312"
    entry_point       = "handle_request"
    docker_repository = google_artifact_registry_repository.functions.id
    source {
      storage_source {
        bucket = var.artifacts_bucket
        object = google_storage_bucket_object.function_source.name
      }
    }
  }
  service_config {
    available_memory      = "512M"
    timeout_seconds       = 300
    min_instance_count    = 0
    max_instance_count    = 2
    service_account_email = var.function_sa
    environment_variables = {
      PROJECT_ID     = var.project_id
      REGION         = var.region
      RESULT_BUCKET  = var.results_bucket
      STATE_BUCKET   = var.state_bucket
      STATUS_TOPIC   = var.status_topic
      AGENT_RESOURCE = google_vertex_ai_reasoning_engine.agent.id
    }
  }
  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic          = var.requests_topic
    service_account_email = var.trigger_sa
    retry_policy          = "RETRY_POLICY_RETRY"
  }
  depends_on = [google_storage_bucket_iam_member.function_state_reader,
    google_artifact_registry_repository_iam_member.function_build_writer,
    google_storage_bucket_iam_member.function_build_source_reader,
  google_storage_bucket_iam_member.function_staged_source_reader]
}

output "agent_resource" { value = google_vertex_ai_reasoning_engine.agent.id }
output "function_name" { value = google_cloudfunctions2_function.request_processor.name }
