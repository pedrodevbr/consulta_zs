import os


class Config:
    JIRA_SERVER = os.getenv("JIRA_SERVER", "https://jira.example.com")
    JIRA_USERNAME = os.getenv("JIRA_USERNAME", "")
    JIRA_PASSWORD = os.getenv("JIRA_PASSWORD", "")
    JIRA_CERT_PATH = os.getenv("JIRA_CERT_PATH", True)
    JIRA_PROJECT = os.getenv("JIRA_PROJECT", "PROJ")
