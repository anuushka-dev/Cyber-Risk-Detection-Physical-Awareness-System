# Cyber Risk Detection & Physical Awareness System

An end-to-end security monitoring system that combines **network intrusion detection** with **physical surveillance context**.

The system uses an ML-based intrusion detection pipeline alongside webcam-based human-context detection, connects both signals through a FastAPI service layer, and supports event logging and Telegram-based alerting.

## Architecture

```text
                  CICIDS2017
                       │
                       ▼
              Feature Processing
                       │
                       ▼
                XGBoost IDS
                       │
                       │
                       ▼
              ┌─────────────────┐
              │  Context Fusion │
              └────────┬────────┘
                       ▲
                       │
                Webcam / OpenCV
                       │
                       ▼
             Human / Physical Context
                       │
                       │
                       ▼
                    FastAPI
                  ┌────┴────┐
                  ▼         ▼
               Dashboard   Alerts
                             │
                          Telegram
```

## What the System Does

### Network Intrusion Detection

The network-security pipeline uses the **CICIDS2017** dataset and an **XGBoost** classifier to identify malicious network activity from traffic features.

```text
Network Traffic
      ↓
Feature Processing
      ↓
Model Inference
      ↓
Attack Classification
      ↓
Confidence / Event
```

### Physical Awareness

The physical-awareness module processes webcam input using **OpenCV** and provides contextual information such as detected people and motion-related signals.

```text
Webcam
  ↓
Frame Processing
  ↓
Human Detection
  ↓
Physical Context
```

### Context Fusion

The system combines cyber and physical signals rather than treating network detection as an isolated classifier.

```text
Cyber Detection
      +
Physical Context
      ↓
Context Fusion
      ↓
Security Event
      ↓
Alert / Logging
```

## Backend API

The FastAPI application provides the service boundary for model inference and system monitoring.

| Endpoint         | Purpose                                       |
| ---------------- | --------------------------------------------- |
| `/`              | Service status                                |
| `/health`        | API and model health                          |
| `/model-info`    | Loaded model metadata                         |
| `/predict`       | Single prediction                             |
| `/predict/batch` | Batch prediction                              |
| `/events`        | Recent prediction events                      |
| `/recent-events` | Recent event feed                             |
| `/logs`          | Recent attack logs                            |
| `/devices`       | Device context                                |
| `/packets`       | Recent packet records                         |
| `/human-context` | Current physical context                      |
| `/camera-frame`  | Latest camera frame                           |
| `/demo/attack`   | Generate a synthetic attack event for testing |

The API also uses request IDs and structured JSONL event logging to make runtime behavior easier to inspect.

## Technology Stack

### Backend

Python · FastAPI · Uvicorn

### Machine Learning

XGBoost · scikit-learn · NumPy · Pandas · SciPy · Joblib

### Computer Vision

OpenCV

### Monitoring & Application

JSON logging · Plotly · Requests · psutil

## Project Structure

```text
api/
├── app.py
├── logging_config.py
├── model_loader.py
└── ...

alerts/
├── alert_engine.py
├── event_logger.py
├── notifier.py
└── notifier_telegram.py

monitoring/
├── config.py
├── feature_extractor.py
├── flow_builder.py
├── human_context.py
├── packet_capture.py
├── realtime_monitor.py
└── virtual_attack.py

train/
└── train_model.py

utils/
├── data_utils.py
└── feature_utils.py

verification/
├── verify_live_api.py
├── verify_logs.py
├── verify_telegram.py
└── run.py
```

## Requirements

* Python 3.9–3.11
* Webcam for the physical-awareness module
* Python dependencies listed in `requirements.txt`

## Installation

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it.

### Windows

```powershell
.venv\Scripts\activate
```

### macOS / Linux

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Create a local `.env` file in the project root.

For Telegram alerts:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_COOLDOWN_SECONDS=120
```

**Never commit `.env` files or Telegram credentials to Git.**

## Run the API

```bash
python -m uvicorn api.app:app --reload
```

## Run the Monitoring Pipeline

```bash
python -m monitoring.realtime_monitor
```

The physical-awareness module requires a connected webcam.

## Run the Frontend

From the frontend directory:

```bash
cd frontend
npm install
npm run dev
```

## Telegram Alerts

Telegram notifications are optional.

The notifier reads credentials from environment variables:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

When an alert is generated, the notification can contain information such as:

* detected attack type
* severity
* source and destination information
* model confidence
* physical context

Keep all bot credentials outside the repository.

## Verification

The repository includes lightweight verification utilities for the running system.

```bash
python verification/verify_live_api.py
python verification/verify_logs.py
python verification/verify_telegram.py
```

These scripts are intended for integration and runtime checks. They are not a replacement for a comprehensive automated test suite.

## Engineering Focus

This project goes beyond a standalone ML notebook.

It demonstrates:

* ML inference behind an API
* batch inference
* model loading and artifact management
* network-flow processing
* computer-vision integration
* context fusion
* structured event logging
* request tracing
* health and model-info endpoints
* alert delivery
* runtime verification

The main engineering idea is to treat the ML model as one component of a larger system rather than the entire application.

## Evaluation

Model performance should be reported from reproducible experiments rather than generic accuracy claims.

A proper evaluation report should include:

```text
Dataset split
Preprocessing
Class distribution
Accuracy
Precision
Recall
F1-score
Confusion matrix
Inference environment
```

Metrics should only be added to this README when the corresponding experiment and evaluation procedure are available in the repository.

## Security & Production Boundaries

This project is a **prototype/research system**, not a production security platform.

Further hardening would include:

* authenticated API access
* restrictive CORS configuration
* stronger automated unit and integration testing
* model versioning and artifact provenance
* reproducible ML experiments
* false-positive and false-negative analysis
* production-grade secret management
* secure telemetry retention
* audit logging
* deployment and incident-response documentation

### Credential History

A historical repository commit contained Telegram credential material.

Any affected Telegram bot credential should be **rotated immediately** and the obsolete secret should be removed from repository history.

## Current Status

### Implemented

* XGBoost-based intrusion detection
* FastAPI inference API
* Batch inference
* Physical-awareness integration
* Context-aware event generation
* Structured runtime logging
* Telegram alerting path
* Verification utilities

### Next Engineering Work

* Reproducible model evaluation artifacts
* Broader automated test coverage
* Secure deployment configuration
* Improved observability
* Historical credential cleanup
* Production security hardening
