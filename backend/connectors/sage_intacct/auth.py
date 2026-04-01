"""Sage Intacct XML-based session authentication."""
from dataclasses import dataclass


@dataclass
class IntacctSession:
    session_id: str
    endpoint: str


def build_login_xml(sender_id, sender_password, company_id, user_id, password, control_id="nexus-auth"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<request>
  <control>
    <senderid>{sender_id}</senderid>
    <password>{sender_password}</password>
    <controlid>{control_id}</controlid>
    <uniqueid>false</uniqueid>
    <dtdversion>3.0</dtdversion>
    <includewhitespace>false</includewhitespace>
  </control>
  <operation>
    <authentication>
      <login>
        <userid>{user_id}</userid>
        <companyid>{company_id}</companyid>
        <password>{password}</password>
      </login>
    </authentication>
    <content>
      <function controlid="get-session"><getAPISession/></function>
    </content>
  </operation>
</request>"""


def build_request_xml(sender_id, sender_password, session_id, control_id, function_xml):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<request>
  <control>
    <senderid>{sender_id}</senderid>
    <password>{sender_password}</password>
    <controlid>{control_id}</controlid>
    <uniqueid>false</uniqueid>
    <dtdversion>3.0</dtdversion>
    <includewhitespace>false</includewhitespace>
  </control>
  <operation>
    <authentication><sessionid>{session_id}</sessionid></authentication>
    <content>
      <function controlid="{control_id}">{function_xml}</function>
    </content>
  </operation>
</request>"""
