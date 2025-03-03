"""
Module for authenticating into and interacting with Acoustic (XML) API

Acoustic API docs can be found here: https://developer.goacoustic.com/acoustic-campaign/reference/overview
"""

from datetime import datetime
from time import sleep
import logging

import jinja2
import requests
import xmltodict  # type: ignore

DATE_FORMAT = "%m/%d/%Y %H:%M:%S"


def _request_wrapper(request_method, request_body):
    _response = request_method(**request_body)
    _response.raise_for_status()
    return _response


class AcousticClient:
    """
    Acoustic Client object for authenticating into and interacting with Acoustic XML API.
    """

    DEFAULT_BASE_URL = "https://api-campaign-us-6.goacoustic.com"
    XML_API_ENDPOINT = "XMLAPI"

    REQUEST_TEMPLATE_PATH = "request_templates"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        base_url: str = None,
        **kwargs,
    ):
        """
        :param client_id: to provide the client identity
        :param client_secret: secret that it used to confirm identity to the API
        :param refresh_token: A long-lived value that the client store,
        the refresh_token establishes the relationship between a specific client and a specific user.

        :return: Instance of AcousticClient class
        """

        self.base_url = base_url or AcousticClient.DEFAULT_BASE_URL
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token = self._generate_access_token()

    def _generate_access_token(self) -> str:
        """
        Responsible for contacting Acoustic XML API and generating an access_token using Oauth method
        to be used for interacting with the API and retrieving data in the following calls.

        :return: A short-lived token that can be generated based on the refresh token.
            A value that is ultimately passed to the API to prove that this client is authorized
            to make API calls on the user’s behalf.

        More info about Acoustic and Oauth:
        https://developer.goacoustic.com/acoustic-campaign/reference/overview#getting-started-with-oauth

        Note: Up to 10 concurrent requests are allowed to our API servers at any given time when using the OAuth method for authentication
        """

        auth_endpoint = "oauth/token"
        url = f"{self.base_url}/{auth_endpoint}"

        _grant_type = "refresh_token"
        _request_body = {
            "grant_type": _grant_type,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
        }

        headers = {
            "content-type": "application/x-www-form-urlencoded",
        }

        request = {
            "url": url,
            "headers": headers,
            "data": _request_body,
        }

        response = _request_wrapper(request_method=requests.post, request_body=request)

        return response.json()["access_token"]

    def _is_job_complete(self, job_id: int, extra_info: str = None) -> bool:
        """
        Checks status of an Acoustic job to generate a report.

        :param job_id: Acoustic job id to check the progress status of

        :return: Returns True if job status in Acoustic is showing as complete
        """

        get_job_status_request_body_template = (
            f"dags/utils/acoustic/{self.REQUEST_TEMPLATE_PATH}/get_job_status.xml.jinja"
        )

        with open(get_job_status_request_body_template, "r") as _file:
            request_body_template = jinja2.Template(_file.read())

        request_body = request_body_template.render(job_id=job_id)

        request = {
            "url": f"{self.base_url}/{self.XML_API_ENDPOINT}",
            "headers": {
                "content-type": "text/xml;charset=utf-8",
                "authorization": f"Bearer {self._access_token}",
            },
            "data": request_body,
        }

        response = _request_wrapper(request_method=requests.post, request_body=request)

        data = xmltodict.parse(response.text)

        job_status = data["Envelope"]["Body"]["RESULT"]["JOB_STATUS"].lower()
        print(
            "INFO: Current status for Acoustic job_id: %s is %s (%s)"
            % (job_id, job_status, extra_info or "")
        )

        return "complete" == job_status

    def generate_report(
        self, request_template: str, template_params: dict, report_type: str,
    ) -> str:
        """
        Extracts a listing of Acoustic Campaign emails that are sent for an organization
        for a specified date range and provides metrics for those emails.


        :param request_template: path to XML template file containing request body template to be used
        :param template_params: values that should be used to render the request template provided

        :return: Returns back a list of rows of data returned by the API call as a dictionary

        More information about the specific API call:
        https://developer.goacoustic.com/acoustic-campaign/reference/reporting#getaggregatetrackingfororg
        """

        supported_report_types = ("raw_recipient_export", "contact_export",)
        if report_type not in supported_report_types:
            pass  # TODO: raise with options

        with open(request_template, "r") as _file:
            request_body_template = jinja2.Template(_file.read())

        request_body = request_body_template.render(**template_params)

        request = {
            "url": f"{self.base_url}/{self.XML_API_ENDPOINT}",
            "headers": {
                "content-type": "text/xml;charset=utf-8",
                "authorization": f"Bearer {self._access_token}",
            },
            "data": request_body,
        }

        start = datetime.now()
        sleep_delay = 20

        response = _request_wrapper(request_method=requests.post, request_body=request)
        data = xmltodict.parse(response.text)

        if report_type == "contact_export":
            job_id = data["Envelope"]["Body"]["RESULT"]["JOB_ID"]
            report_loc = data["Envelope"]["Body"]["RESULT"]["FILE_PATH"]
        elif report_type == "raw_recipient_export":
            job_id, report_loc = data["Envelope"]["Body"]["RESULT"]["MAILING"].values()

        while not self._is_job_complete(job_id=job_id, extra_info=report_type):
            sleep(sleep_delay)

        logging.info(f"{report_type} generation complete. Report location: {report_loc}. Time taken: {datetime.now() - start}")

        return
