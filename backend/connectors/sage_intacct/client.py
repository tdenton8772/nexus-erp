"""Low-level async HTTP client for the Sage Intacct XML Gateway API."""
import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Optional

import httpx

from .auth import IntacctSession, build_login_xml, build_request_xml

logger = logging.getLogger(__name__)
INTACCT_GATEWAY = "https://api.intacct.com/ia/xml/xmlgw.phtml"


class IntacctClient:
    def __init__(self, company_id, user_id, password, sender_id, sender_password, base_url=INTACCT_GATEWAY):
        self.company_id = company_id
        self.user_id = user_id
        self.password = password
        self.sender_id = sender_id
        self.sender_password = sender_password
        self.base_url = base_url
        self._session: Optional[IntacctSession] = None
        self._http: Optional[httpx.AsyncClient] = None

    async def authenticate(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)
        login_xml = build_login_xml(self.sender_id, self.sender_password, self.company_id, self.user_id, self.password)
        resp = await self._http.post(self.base_url, content=login_xml.encode(), headers={"Content-Type": "application/xml"})
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        session_el = root.find(".//sessionid")
        endpoint_el = root.find(".//endpoint")
        if session_el is None or not session_el.text:
            error_el = root.find(".//errormessage/error/description2")
            raise RuntimeError(f"Intacct auth failed: {error_el.text if error_el is not None else resp.text}")
        self._session = IntacctSession(session_id=session_el.text, endpoint=endpoint_el.text if endpoint_el is not None else self.base_url)

    async def close_session(self) -> None:
        if self._http:
            await self._http.aclose()
        self._session = None

    async def _post_xml(self, function_xml: str) -> ET.Element:
        if not self._session:
            await self.authenticate()
        payload = build_request_xml(self.sender_id, self.sender_password, self._session.session_id, str(uuid.uuid4())[:8], function_xml)
        resp = await self._http.post(self._session.endpoint, content=payload.encode(), headers={"Content-Type": "application/xml"})
        resp.raise_for_status()
        return ET.fromstring(resp.text)

    async def get_object_definition(self, object_name: str) -> dict:
        root = await self._post_xml(f"<lookup><object>{object_name}</object></lookup>")
        fields = [{"id": f.findtext("ID",""), "label": f.findtext("LABEL",""), "datatype": f.findtext("DATATYPE","TEXT"), "required": f.findtext("REQUIRED","false")=="true"} for f in root.findall(".//Field")]
        return {"object_name": object_name, "fields": fields}

    async def query(self, object_name, modified_since=None, page_size=500, offset=0):
        filters = ""
        if modified_since:
            ts = modified_since.strftime("%m/%d/%Y %H:%M:%S")
            filters = f"<filter><greaterthan><field>WHENMODIFIED</field><value>{ts}</value></greaterthan></filter>"
        fn_xml = f"<query><object>{object_name}</object><select><field>*</field></select>{filters}<pagesize>{page_size}</pagesize><offset>{offset}</offset></query>"
        root = await self._post_xml(fn_xml)
        records = [{child.tag: child.text for child in obj_el} for obj_el in root.findall(f".//{object_name}")]
        total_el = root.find(".//totalcount")
        total = int(total_el.text) if total_el is not None else len(records)
        next_offset = offset + page_size
        return records, str(next_offset) if next_offset < total else None

    async def upsert(self, object_name, data):
        fields_xml = "".join(f"<{k}>{v}</{k}>" for k, v in data.items() if v is not None)
        fn_xml = f"<upsert><object>{object_name}</object><key>RECORDNO</key><{object_name}>{fields_xml}</{object_name}></upsert>"
        root = await self._post_xml(fn_xml)
        return {"status": root.findtext(".//status","unknown"), "key": root.findtext(".//key"), "errormessage": root.findtext(".//errormessage/error/description2")}
