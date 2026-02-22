# Terraform config for Home Facelift Copilot — GCP Firestore for persistent memory
# Usage:
#   cd terraform
#   terraform init
#   terraform apply

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "capella-vertex-rag"
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "europe-west1"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable Firestore API
resource "google_project_service" "firestore" {
  project = var.project_id
  service = "firestore.googleapis.com"

  disable_on_destroy = false
}

# Firestore database (Native mode) for persistent project memory
resource "google_firestore_database" "facelift" {
  project     = var.project_id
  name        = "facelift-memory"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # Free tier: 1GB storage, 50K reads/day, 20K writes/day
  delete_protection_state = "DELETE_PROTECTION_DISABLED"
  deletion_policy         = "DELETE"

  depends_on = [google_project_service.firestore]
}

# Enable Cloud Storage API
resource "google_project_service" "storage" {
  project = var.project_id
  service = "storage.googleapis.com"

  disable_on_destroy = false
}

# GCS bucket for uploaded + generated images
resource "google_storage_bucket" "images" {
  project       = var.project_id
  name          = "${var.project_id}-facelift-images"
  location      = var.region
  storage_class = "STANDARD"
  force_destroy = true

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type = "Delete"
    }
  }

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }

  depends_on = [google_project_service.storage]
}

# Make images publicly readable (for frontend display)
resource "google_storage_bucket_iam_member" "public_read" {
  bucket = google_storage_bucket.images.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

output "firestore_database" {
  value = google_firestore_database.facelift.name
}

output "images_bucket" {
  value = google_storage_bucket.images.name
}

output "images_bucket_url" {
  value = "https://storage.googleapis.com/${google_storage_bucket.images.name}"
}

output "project_id" {
  value = var.project_id
}
