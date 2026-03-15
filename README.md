# 50ohm Pool Question Review Tool

## Overview
This tool is part of the Swiss 50ohm platform and is used to review the question pool for the platform. it is used for reviewing the French and Italian translations of the original question pool as well as any changes that need to be applied to the German version. The application is a web-based tool built with FastAPI and runs serverless on Google Cloud Run.

![Screenshot](/images/screenshot_review_tool.png)

## How it works
Users authenticate with their GitHub account, and the resulting OAuth2 token allows the application to retrieve questions and push changes to the repository containing the source data. The repository is defined in a `.env` file, with an example provided as `.env.example`.

Each question is stored in its own JSON file, and review comments are logged in the `HB.comments` field of the corresponding JSON. The `WIP` branch contains the latest version with all ongoing changes, which are always compared to the commit tagged `FR_orig_DeepL`. Original questions in German are taken from the commit `german_orig`. The `fragenkatalog3b.json` file is used for creating the table of contents; questions in this file are not used as they do not represent the latest state of our process.

Through the web interface, users can view questions, add review comments, and submit updates back to the repository.

## Deployment
A new container image is built and deployed automatically when changes are merged into the `deploy` branch, making deployment to Google Cloud Run seamless. To run the tool locally, you need to install the requirements as listed in `requirements.txt` and create a `.env` file based on `.env.example` where you provide the required environment variables.
