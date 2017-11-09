#!/usr/bin/env python

import sys
import json
import urllib
import urllib2
import cookielib
import logging
import argparse
import traceback

"""

        Usage:

        With this library you can create a CIC Data-access-Object and pull
        data from CIC.

        Example:.

        cicObj = cic.CicDaO()

        response = cicObj.getTenantByUid(uid)
        response = cicObj.getSystemByNAme("epmprodXX")
        response = cicObj.getTenantByName(systemName,description)

        Most functions like the ones above return a dictionary which
        contains the tenant data. For a full list of key/value pairs see
        the TMS documentation.

        {
                "tenantId": "XY",
                "ownerEmail": "help_me_out@mailinator.com",
                "ownerFirstName": "John",
                "ownerLastName": "Doe",
                "url": "https://epmqaXXX.int.sap.hana.ondemand.com:443/t/XY",
                "publicFqdn": "help-me-out-mailinator-com.canary.sapbusinessobjects.cloud",
                "schema": "TENANT_XY",
                .......
        }

        These dictionary's can simple be read like:

        tenantId = response["tenantId"]

        Some functions a uid which can then be parsed to a function like
        getSystemByUid() to get the data

        response = cicObj.getTenantByUid(uid)

"""

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

CIC_SYSTEM_ENDPOINT = "/TMS/systems"
CIC_TENANT_ENDPOINT = "/TMS/tenants"
CIC_INSTANCE_LIST_ENDPOINT = "/TMS/instancesList"

# S_ = System parameter
S_LANDSCAPE = "landscape="
S_GROUP = "updateGroup="
S_CLASSIFICATION = "classification="

# T_ = Tenant parameter
T_SYSTEM = "system="
T_CUSTOMER_NAME = "customerName="
T_ERP_NUMBER = "erpnumber="
T_DESCRIPTION = "description="
T_CLASSIFICATION = "classification="

cic_argparser = argparse.ArgumentParser(add_help=False)
cic_argparser.add_argument("--cic-user", help="CIC Userid ( Your D/I number )", required=True)
cic_argparser.add_argument("--cic-password", help="CIC Password", required=False)
cic_argparser.add_argument("--cic-url", help="CIC URL (https://cic.mo.sap.corp): ", required=False)

class CicDaO(object):

        def __init__(self,cicUser,cicPassword,cicUrl="https://cic.mo.sap.corp"):

                logger.debug("Initializing CICDaO with url: {}".format(cicUrl))
                self.httpHandler = HttpHandler(cicUser,cicPassword,cicUrl)
                self.helperObject = HelperObject()
                self.cicUrl = cicUrl
                self.cicUser = cicUser

        def hasPrivilege(self, privilege, groupid=None):

            """
            CIC Query to verify a users privileges to perform tasks
            like Manipulating data or if the user is member of a
            specific cic user group (as of 2017.11 FACTORY/EUDP)
            :param privilege:   String
            :param groupid:     Integer (Optional)
            :rtype:             boolean
            """

            if groupid is None:
                # Privilege needs to be a string, for example: "TMS.Systems.Update"
                url = "/hasPrivilege?{}".format(urllib.urlencode({ "privilege" : privilege }))
            else:
                # groupid needs to be of type integer, e.g. "1" , check CIC Administration > Groups
                url = "/hasPrivilege?{}".format(urllib.urlencode({ "privilege" : privilege, "groupid" : groupid }))
            try:
                response = self.httpHandler.sendHttpRequest(url)
            except urllib2.HTTPError as e:

                logger.debug(traceback.format_exc())

                # 403 is a valid return code when the privilege is not available
                c = e.code
                if c == 403:

                    logger.debug("Response code: {}, response body: {}".format(e.code, e.read()))
                    return False

                else:
                    raise
            else:
                c = response.getcode()

                if c == 200:
                    return True

                else:

                    body = e.read()
                    logger.debug("Response code: {}, response body: {}".format(e.code, body))
                    raise AssertionError(
                        "Got unexpected http return code: {} when calling {}".format(
                            c, url))


        def getCicMemberList(self, groupname,listofroles,fieldselector=None):

            """
                This function creates an odata query string which is used to
                to request a list of d/i-users which that are part of specified
                access group and posssess the associated privilege. Returns an
                array of users with the requested key field or full metadata if no
                selector was set. Array will be empty if the request was malformed

            :param groupname:         Name of the group as found in CIC (case-sensitive)
            :param listofroles:       Assigned Role as found in CIC (case-sensitive)
            :param fieldselector:     Specify none or one key field that you want to
                                      have returned for each entry of the result. If you
                                      don't specify a key field all metadata entries will be
                                      returned for each result
            :rtype:                   String / dict
            """

            urlEndpoint      = "/odata/Users?$filter="
            queryString = ""
            memberList = ""

            # Build a query string based on the number of given roles via OR concatenation
            if len(listofroles) > 1:
                for role in listofroles:

                    if not queryString:
                        queryString+="groupname eq '"+groupname+"' and role eq '"+role+"'"
                    else:
                        queryString+=" or groupname eq '"+groupname+"' and role eq '"+role+"'"
                queryString         = urllib.pathname2url(queryString)

            # or create only one query
            else:
                queryString      = urllib.pathname2url("groupname eq '"+groupname+"' and role eq '"+listofroles[0]+"'")

            # Append a field selector if given so only this one key field is returned for each entry
            if fieldselector is not None:
                selectedField    = "&$select="+fieldselector
                urlComplete      = urlEndpoint+queryString+selectedField
            # else return whole key set for each result
            else:
                urlComplete      = urlEndpoint+queryString

            try:
                response = self.httpHandler.sendHttpRequest(urlComplete)

            except urllib2.HTTPError as e:

                logger.debug(traceback.format_exc())

            else:

                responseCode = response.getcode()
                if responseCode == 200:
                    response = json.loads(response.read())
                    if not response["value"]:
                        logger.debug("CIC OData query returned an empty result-set. Check used parameters")
                        return memberList
                    else:
                        # read key value for each result and create a new clean result array
                        if fieldselector is not None:
                            for item in response["value"]:
                                # Technical users have no associated d-number so dont add them to the member list
                                if item[fieldselector] is not None:
                                    memberList+=" "+item[fieldselector].encode("ascii","ignore")
                            return memberList
                        # return the whole payload as is
                        else:
                            return response
                else:
                    body = e.read()
                    logger.debug("Response code: {}, response body: {}".format(responseCode, body))
                    raise AssertionError("Got unexpected http return code: {} when calling {}".format(responseCode, urlComplete))



        def getSystemByUid(self,uid):

                """  Returns complete system information of the specified system by uid
                :param uid:     System Unique identifier
                :rtype:         dict
                """

                logger.debug("Call to getSystemByUid - uid: {}".format(uid))
                try:
                    response = self.httpHandler.sendHttpRequest(CIC_SYSTEM_ENDPOINT+"?uuid="+uid)

                except urllib2.HTTPError as e:

                    logger.debug(traceback.format_exc())

                    if e.code == 404:

                        body = e.read()
                        logger.debug("Response code: {}, response body: {}".format(e.code, body))
                        raise KeyError(
                                "System with uid {} not found in TMS, {}".format(uid, body),
                                "CIC_SYSTEM_UUID_NOT_FOUND_ERR")

                    elif e.code == 403:

                        body = e.read()
                        logger.debug("Response code: {}, response body: {}".format(e.code, body))
                        raise RuntimeError(
                        "User {} has no permission to look up 'systems' in {} {}".format(self.cicUser, self.cicUrl, body),
                        "CIC_NO_ACCESS"
                        )

                    else:
                        raise
                else:
                    responseString = response.read()
                    return json.loads(responseString)


        def getSystemByName(self,systemName):

                """  Returns complete system information of the specified system by name
                Currently in TMS v2 a separate lookup is needed for the UID to get all
                information about a system
                :param systemName:      unique system name
                :rtype:                 dict
                """

                logger.debug("Call to getSystemByName - systemName: {}".format(systemName))
                try:

                    response = self.httpHandler.sendHttpRequest(
                            CIC_SYSTEM_ENDPOINT+"?"+
                            urllib.urlencode({ "name": systemName }))

                except urllib2.HTTPError as e:

                    logger.debug(traceback.format_exc())

                    if e.code == 404:

                        body = e.read()
                        logger.debug("Response code: {}, response body: {}".format(e.code, body))
                        flag = _checkSystemNotFound(body)
                        if flag == True:
                            raise KeyError(
                                "System with name '{}' was not found in TMS because it does not exist, {}".format(systemName, body),
                                "CIC_SYSTEM_NOT_FOUND_ERR")
                        else:
                            raise IOError(
                                "System with name '{}' was not found in TMS because of network/communication error, {}".format(systemName, body),
                                "CIC_SYSTEM_COMMUNICATION_NETWORK_ERR")

                    elif e.code == 403:

                        body = e.read()
                        logger.debug("Response code: {}, response body: {}".format(e.code, body))
                        raise RuntimeError(
                        "User {} has no permission to look up the specified system {} in {} {}".format(self.cicUser,systemName, self.cicUrl, body),
                        "CIC_NO_ACCESS"
                        )

                    else:
                        raise
                else:
                    responseString = response.read()
                    return json.loads(responseString)

        def getSystemUidBySystemName(self,systemName):

                """ Retrieves a system UID from CIC for any given System known to TMS
                :param systemName:      Unique system name
                :rtype:                 unicode string
                """

                systemObj = self.getSystemByName(systemName)
                return systemObj["uuid"]

        def getTenantByUid(self,uid):

                """
                Returns a json object returning all available information about
                the provided tenant uid

                :param uid:     Unique tenant identifier
                :rtype:         dict
                """

                logger.debug("Call to getTenantByUid - uid: {}".format(uid))

                try:
                    response = self.httpHandler.sendHttpRequest(CIC_TENANT_ENDPOINT+"?uuid="+uid)
                except urllib2.HTTPError as e:

                    logger.debug(traceback.format_exc())

                    if e.code == 404:

                        body = e.read()
                        logger.debug("Response code: {}, response body: {}".format(e.code, body))
                        raise KeyError("Tenant with uuid {} could not be found in TMS.".format(uid),"CIC_TENANT_UID_NOT_FOUND_ERR")

                    elif e.code == 403:

                        body = e.read()
                        logger.debug("Response code: {}, response body: {}".format(e.code, body))
                        raise RuntimeError(
                        "User {} has no permission to look up 'tenants' in {} {}".format(self.cicUser, self.cicUrl, body),
                        "CIC_NO_ACCESS"
                        )

                    else:
                        raise
                else:
                    responseString = response.read()
                    return json.loads(responseString)


        def getTenantByName(self,tenantName,description):

                """
                Returns exactly one tenant defined by the system it resides on
                and the description
                Dependency: description field needs to show the Tenant ID

                :param description:     Content of the description field
                :rtype:                 dict
                """

                url = CIC_TENANT_ENDPOINT + "?" + urllib.urlencode(
                        {
                            "instanceName":tenantName,
                            "description":description
                        })

                logger.debug("Calling url {}".format(url))

                try:
                    response = self.httpHandler.sendHttpRequest(url)
                except urllib2.HTTPError as e:

                    logger.debug(traceback.format_exc())

                    if e.code == 404:

                        body = e.read()
                        logger.debug("Response code: {}, response body: {}".format(e.code, body))
                        raise KeyError(
                            "Tenant '{}' could not be found in TMS".format(tenantName),
                            "CIC_TENANT_LOOKUP_ERROR")

                    elif e.code == 403:

                        body = e.read()
                        logger.debug("Response code: {}, response body: {}".format(e.code, body))
                        raise RuntimeError(
                        "User {} has no permission to look up 'tenants' in {} {}".format(self.cicUser, self.cicUrl, body),
                        "CIC_NO_ACCESS"
                        )

                    else:
                        raise
                else:
                    responseString = response.read()
                    return json.loads(responseString)


        def getLandscapesByGroup(self, groupName):
            logger.debug("Call to getLandscapeByGroup - groupName: {}".format(groupName))
            CIC_GROUP_ENDPOINT = "/odata/Landscapes?$filter=groupname%20eq%20%27{}%27&$select=landscape".format(groupName)

            try:
                response = self.httpHandler.sendHttpRequest(CIC_GROUP_ENDPOINT)
            except urllib2.HTTPError as e:
                logger.debug(traceback.format_exc())
            else:
                responseString = response.read()
                return json.loads(responseString)


        def getInstanceList(self):

            logger.debug("Call to getInstanceList:")

            try:
                response = self.httpHandler.sendHttpRequest\
                    (CIC_SYSTEM_ENDPOINT + "?details[]=name&details[]=updateGroup" + "&enforce_complete_results=true")

            except urllib2.HTTPError as e:

                logger.debug(traceback.format_exc())

                if e.code == 403:

                    body = e.read()
                    logger.debug("Response code: {}, response body: {}".format(e.code, body))
                    raise RuntimeError(
                    "User {} has no permission to look up 'systems' in {} {}".format(self.cicUser, self.cicUrl, body),
                    "CIC_NO_ACCESS"
                    )

                else:
                    raise

            else:
                responseString = response.read()
                return json.loads(responseString)


        def getAllTenants(self):

            logger.debug("Call to getAllTenants:")

            try:
                response = self.httpHandler.sendHttpRequest(CIC_TENANT_ENDPOINT + "?details[]=consumerAccountDisplayName" + "&enforce_complete_results=true")

            except urllib2.HTTPError as e:

                logger.debug(traceback.format_exc())
                if e.code == 403:

                    body = e.read()
                    logger.debug("Response code: {}, response body: {}".format(e.code, body))
                    raise RuntimeError(
                    "User {} has no permission to look up 'tenants' in {} {}".format(self.cicUser, self.cicUrl, body),
                    "CIC_NO_ACCESS"
                    )

                else:
                    raise

            else:
                responseString = response.read()
                return json.loads(responseString)

        def getSystemsByFilter(self, filterSet, detailsNames):

            logger.debug("Call to getSystemsByFilter:")

            paramDict = {}

            if filterSet is not None:
                paramDict.update(filterSet)

            if detailsNames is not None:
                paramDict.update({ 'details[]' : detailsNames } ) # encode an array of values

            if len(paramDict) > 0:
                paramDict.update({ "enforce_complete_results" : "true" } )
                req = CIC_SYSTEM_ENDPOINT + "?" + urllib.urlencode(paramDict, True) # bool "True" is for arrays

            else:
                req = CIC_SYSTEM_ENDPOINT

            try:
                response = self.httpHandler.sendHttpRequest(req)

            except urllib2.HTTPError as e:

                logger.debug(traceback.format_exc())
                if e.code == 403:

                    body = e.read()
                    logger.debug("Response code: {}, response body: {}".format(e.code, body))
                    raise RuntimeError(
                    "User {} has no permission to look up 'systems' in {} {}".format(self.cicUser, self.cicUrl, body),
                    "CIC_NO_ACCESS"
                    )

                else:
                    raise

            else:
                responseString = response.read()
                return json.loads(responseString)

        def getTenantsByFilter(self, filterSet, detailsNames):

            logger.debug("Call to getTenantsByFilter:")

            paramDict = {}

            if filterSet is not None:
                paramDict.update(filterSet)

            if detailsNames is not None:
                paramDict.update({ 'details[]' : detailsNames } ) # encode an array of values

            if len(paramDict) > 0:
                paramDict.update({ "enforce_complete_results" : "true" } )
                req = CIC_TENANT_ENDPOINT + "?" + urllib.urlencode(paramDict, True) # bool "True" is for arrays

            else:
                req = CIC_TENANT_ENDPOINT


            # We are currently not catching any exception here, because we don't know about the possible TMS error conditions 
            try:
                response = self.httpHandler.sendHttpRequest(req)

            except urllib2.HTTPError as e:

                logger.debug(traceback.format_exc())

                if e.code == 403:

                    body = e.read()
                    logger.debug("Response code: {}, response body: {}".format(e.code, body))
                    raise RuntimeError(
                    "User {} has no permission to look up 'tenants' in {} {}".format(self.cicUser, self.cicUrl, body),
                    "CIC_NO_ACCESS"
                    )

                else:
                    raise

            else:
                responseString = response.read()
                return json.loads(responseString)

        def changeTenantMetadata(self,systemName,tenantDescription,parameter,value):

            """
            Manipulate Systems metadata using the TMS v2 API. All parameters
            can be changed (see TMSv2 API for details).
            :param: systemName          Unique name of the system/instance
                                        (epmprodxx)
            :param: tenantDescription   description e.g. MT1
            :param: parameter           name of the parameter to change
            :param: value               New value of the parameter
            :rtype: None,Tenant Object  Depending on the call getSystemByName
                                        the function either returns None or a
                                        System Object if successful
            """

            tenantObj = self.getTenantByName(systemName,tenantDescription)

            # build payload
            payload = {
                        "versionUuid": tenantObj["versionUuid"],
                        "uuid": tenantObj["uuid"],
                        parameter: value
                    }
            logger.debug("Call to changeTenantMetadata - systemName: {} tenant description: {} parameter: {} value: {}".format(systemName,tenantDescription,parameter,value))
            logger.debug(" Next line contains json payload")
            logger.debug(payload)

            try:
                response =  self.httpHandler.sendHttpRequest(CIC_TENANT_ENDPOINT, payload, "PATCH", "metadata")

            except urllib2.HTTPError as e:

                logger.debug(traceback.format_exc())

                if e.code == 403:

                    body = e.read()
                    logger.debug("Response code: {}, response body: {}".format(e.code, body))
                    raise RuntimeError(
                    "User {} has no permission to update 'tenants' in {} {}".format(self.cicUser, self.cicUrl, body),
                    "CIC_NO_ACCESS"
                    )

                else:

                    body = e.read()
                    logger.debug("Response code: {}, response body: {}".format(e.code, body))
                    raise RuntimeError(
                            "An http error occured during tenant metatdata update: "
                            "{}, Response body: {}".format(e, body),
                            "CIC_TENANT_METADATA_UPDATE_ERR")

            else:

                responseString = response.read()
                returnDict = json.loads(responseString)
                logger.debug("Return dict is: {}".format(returnDict))

                rc = self._validateResponse(returnDict, parameter, value)
                if rc == 0 or rc == 1:
                    return returnDict
                elif rc == 2:
                    raise RuntimeError(
                    "Tenant metadata update failed. "
                    "Parameter '{}' not written. Maybe invalid parameter.".format(parameter),
                    "CIC_TENANT_METADATA_UPDATE_NOTWRITE")
                elif rc == 3:
                    returnValue = returnDict[parameter]
                    raise RuntimeError(
                        "Tenant metadata update failed. "
                        "Parameter '{}' written but different return value: {} != {}.".format(
                            parameter, value, returnValue),
                        "CIC_TENANT_METADATA_UPDATE_MISMATCH")


        def changeMultiFieldsTenantMetadata(self, systemName, tenantDescription, dictParamValue):
            tenantObj = self.getTenantByName(systemName,tenantDescription)
            payload = {
                        "versionUuid": tenantObj["versionUuid"],
                        "uuid": tenantObj["uuid"]
                    }
            if dictParamValue != None:
                payload.update(dictParamValue)

            params = urllib.urlencode({'uuid' : tenantObj["uuid"]})
            endpoint = CIC_TENANT_ENDPOINT + '?' + params

            try:
                response = self.httpHandler.sendHttpRequest(endpoint, payload, "PATCH", "metadata")
            except urllib2.HTTPError as e:
                logger.debug(traceback.format_exc())
                body = e.read()
                logger.debug("Response code: {}, response body: {}".format(e.code, body))
                raise RuntimeError(
                            "An http error occured during multi-fields tenant metatdata update: "
                            "{}, Response body: {}".format(e, body),
                            "CIC_MULTI_FIELDS_TENANT_METADATA_UPDATE_ERR")
            else:
                responseString = response.read()
                returnDict = json.loads(responseString)
                logger.debug("Return dict is: {}".format(returnDict))

                for parameter, value in dictParamValue.iteritems():
                    rc = self._validateResponse(returnDict, parameter, value)
                    if rc == 2 or rc == 3:
                        break

                if rc == 0 or rc == 1:
                    return returnDict
                elif rc == 2:
                    raise RuntimeError(
                    "Tenant multi-fields metadata update failed. "
                    "Parameter '{}' not written. Maybe invalid parameter.".format(parameter),
                    "CIC_MULTI_FIELDS_TENANT_METADATA_UPDATE_NOTWRITE")
                elif rc == 3:
                    returnValue = returnDict[parameter]
                    raise RuntimeError(
                        "Tenant multi-fields metadata update failed. "
                        "Parameter '{}' written but different return value: {} != {}.".format(
                            parameter, value, returnValue),
                        "CIC_MULTI_FIELDS_TENANT_METADATA_UPDATE_MISMATCH")


        def changeSystemMetadata(self,systemName,parameter,value):

            """
            Manipulate System metadata in TMS v2. All parameters
            can be changed (see TMSv2 API for details).
            :param: systemName          Unique name of the system/instance
                                        (epmprodxx)
            :param: parameter           System metadata parameter e.g.
                                        "underMaintenance"
            :param: value               New value of the parameter
            :rtype: None,System Object  Depending on the call getSystemByName
                                        the function either returns None or a
                                        System Object if successful
            """

            logger.debug("Call to changeTenantMetadata - systemName: {} parameter: {} value: {}".format(systemName, parameter, value))
            logger.debug("Next line contains json payload")

            sysObj = self.getSystemByName(systemName)

            payload = {
                        "versionUuid": sysObj["versionUuid"],
                        "uuid": sysObj["uuid"],
                        "landscape": sysObj["landscape"],
                        parameter: value
                    }
            logger.debug(payload)

            try:
                response =  self.httpHandler.sendHttpRequest(CIC_SYSTEM_ENDPOINT, payload, "PATCH", "metadata")
            except urllib2.HTTPError as e:

                logger.debug(traceback.format_exc())

                if e.code == 403:

                    body = e.read()
                    logger.debug("Response code: {}, response body: {}".format(e.code, body))
                    raise RuntimeError(
                    "User {} has no permission to update 'systems' in {} {}".format(self.cicUser, self.cicUrl, body),
                    "CIC_NO_ACCESS"
                    )

                else:

                    body = e.read()
                    logger.debug("Response code: {}, response body: {}".format(e.code, body))
                    raise RuntimeError(
                            "An http error occured during system metatdata update: "
                            "{}, Response body: {}".format(e, body),
                            "CIC_SYSTEM_METADATA_UPDATE_ERR")

            else:

                responseString = response.read()
                returnDict = json.loads(responseString)
                logger.debug("Return dict is: {}".format(returnDict))

                rc = self._validateResponse(returnDict, parameter, value)
                if rc == 0 or rc == 1:
                    return returnDict
                elif rc == 2:
                    raise RuntimeError(
                    "System metadata update failed. "
                    "Parameter '{}' not written. Maybe invalid parameter.".format(parameter),
                    "CIC_SYSTEM_METADATA_UPDATE_NOTWRITE")
                elif rc == 3:
                    returnValue = returnDict[parameter]
                    raise RuntimeError(
                        "System metadata update failed. "
                        "Parameter '{}' written but different return value: {} != {}.".format(
                            parameter, value, returnValue),
                        "CIC_SYSTEM_METADATA_UPDATE_MISMATCH")


        def _validateResponse(self, returnDict, parameter, value):
            logger.debug("Call to _validateResponse - returnDict: {} parameter: {} value: {}".format(returnDict, parameter, value))

            if value == "":
                return 1

            try:
                returnValue = returnDict[parameter]
            except KeyError:
                return 2

            validBool = ( str(returnValue) == str(value) )
            if validBool:
                logger.debug("Return dictionary: {}".format(returnDict))
                return 0
            else:
                return 3


        def addSystemEntryToCIC(self,payload):

            """
            Creates a new system entry in TMS using CIC
            :param: payload         Json payload which is beeing sent to CIC
            :rtype: json response   json response from CIC
            """

            response = None
            # Verify payload format and get system name needed for the request
            if payload is not None:
                try:
                    response = self.getSystemByName(payload["name"])
                except KeyError as e:
                    if e.args[1] == "CIC_SYSTEM_NOT_FOUND_ERR":
                        pass
                    else:
                        raise
            else:
                raise RuntimeError("AddSystemEntryToCIC - Payload is empty","CIC_ADD_SYSTEM_EMPTY_PAYLOAD_ERR")

            # check whether the system already exists and only continue if not
            if response is not None:
                raise RuntimeError("System specified in the payload already exists","CIC_SYSTEM_ALREADY_EXISTS_ERR")
            else:
                logger.debug("Sending POST request to {}, payload: {}".format(CIC_SYSTEM_ENDPOINT, payload))
                response =  self.httpHandler.sendHttpRequest(CIC_SYSTEM_ENDPOINT,payload,"POST")
                if response is not None:
                    return self.helperObject._evaluateHttpConnStatus(response.getcode(),response)
                else:
                    raise RuntimeError("Unable to add system to CIC","CIC_SYSTEM_ENTRY_ERR")


        def createOrcaTenant(self,payload):

            """
            Create an Orca Tenant on any instance by providing the payload. The minimum required
            payload looks like this. You can copy this and just have to replace the placeholders:

            payload = {
                "system"                : <call getSystemUidBySystemName(instance) for the system UUID>,
                "description"           : <enter description>,
                "landscape"             : <call getSystemByName(instance) -> response['landscape'])>,
                "ownerFirstName"        : <enter firstname>,
                "ownerLastName"         : <lastname>,
                "ownerEmail"            : <ownermail>,
                "classification"        : <classification>,
                "useCloudId"            : <usecloudid - true/false>,
                "internalContactEmail"  : <use blackhole dl "DL_5804854D5F99B7F13F00001A@exchange.sap.corp" or replace>,
                "useAppRouter"          : <useapprouter - true/false>,
                'license'               : { 'thresholdProfessionalUser': '0'}
                                         License field cant be empty. use this placeholder if you dont want to specify more
            }
            """
            response = None
            # Check if tenant with that name already exists
            systemObj = self.getSystemByUid(payload["system"])
            try:
                # Systemname and tenant description always determine a specific tenant
                response =  self.getTenantByName(systemObj["name"],payload["description"].upper())
            except KeyError as e:
                if e.args[1] == "CIC_TENANT_LOOKUP_ERROR":
                    response = None
                    pass
                else:
                    raise
            try:
                # TMS delivers always a non-empty body if something was found
                if response:
                    if response["description"] == payload["description"].upper():
                        raise RuntimeError("*** INFO *** Tenant already exists","CIC_CREATE_TENANT_ERROR")
                # TMS delivers an empty body if nothing is found
                elif response is None:
                    print "*** INFO *** Starting tenant creation"
                    response = self.httpHandler.sendHttpRequest(CIC_TENANT_ENDPOINT,payload,"POST")
                    status = response.getcode()
                    if status == 202:
                        print "*** INFO *** Tenant creation successfully triggered"

            except RuntimeError as e:
                print e.args[0]
            except AttributeError as e:
                print "*** INFO *** Discarding request.Please wait until tenant creation finishes before sending another request"

class HelperObject(object):

        def _evaluateHttpConnStatus(self,statusCode,response=None):

                """ Evaluate the Status Code of a given response and return 1 for OK
                or a Runtime error + message
                Also performs json decoding and returns a readable dict
                :param statusCode:      status code of the http request
                :rtype:                 None if no response object was passed
                                        otherwise a tenant/system dict is
                                        returned which holds all data
                """

                logger.debug("Status Code: {}".format(statusCode))
                if statusCode in (200, 201,202):

                    if response is None:

                        logger.debug("Response is None even when status code is {}.",statusCode)
                        return False

                    else:

                        responseString = response.read()
                        return json.loads(responseString)

                else:
                    if statusCode == "500":
                        raise RuntimeError ("Invalid UUID string passed to TMS - Status-Code: {}".format(statusCode),"CIC_INVALID_UUID_ERR")
                    else:
                        raise RuntimeError ("Unhandled http response code {}".format(statusCode),"CIC_UNHANDLED_ERR")

        def removePrefix(self,text, prefix):

                """ Remove prefix from a substring
                """

                return text[text.startswith(prefix) and len(prefix):]

        def getCloudhost(self,systemObject):

                """
                Manually extract/build the cloudhost information
                """

                prefix = "https://"+systemObject["name"]+systemObject["hcpAccount"]+"."
                return self.removePrefix(systemObject["rootUrl"],prefix)


class HttpHandler(object):

    def __init__(self,cicUser, cicPassword,cicUrl):

            """
            Handler needs Authentication parameters and the url to call
            """

            self.cicUser = cicUser
            self.cicPassword = cicPassword
            self.cicUrl = cicUrl

            self.login()

    def login(self):
        """
        tries to log in 
        stores self.opener on success
        raises exception on failure
        """
        cj = cookielib.CookieJar()
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
        loginData = urllib.urlencode({'username' : self.cicUser, 'password' : self.cicPassword})

        try:
            cookie = opener.open(self.cicUrl+"/login",loginData)
        except urllib2.HTTPError as e:

            logger.debug(traceback.format_exc())

            if e.code == 401:

                body = e.read()
                logger.debug("Response code: {}, response body: {}".format(e.code, body))
                raise RuntimeError(
                    "Could not log on to {}, {}".format(self.cicUrl, body),
                    "CIC_AUTHORIZATION_ERROR")
            else:
                raise

        else:
            self.opener = opener
            logger.debug("Cookie aquired for user {}".format (cookie.read()))


    def createHttpRequest(self, endpoint, payload=None, method=None, xDepth=None):

            """ Creates a request payload depending on the
            specified parameters. If payload is provided its
            assumend that a HTTP PATCH has to be performed at a
            CIC endpoint

            endpoint is in this function the path url plus parameters
            Take care to do proper url encoding for path
            Url encoding is already done for payload ( sorry for the assymetric design )
            """

            logger.debug("Endpoint: {}".format(endpoint))

            if endpoint is None:
                raise TypeError("expected CIC endpoint url but received None","CIC_WRONG_ARGUMENT_TYPE_ERR")

            # if no playload provided always do HTTP GET by default
            if payload is None:
                logger.debug("Preparing HTTP GET")
                request = urllib2.Request(self.cicUrl+endpoint)

            elif ((payload is not None) and (method == "POST")):
                logger.debug("Preparing HTTP Post")
                data = json.dumps(payload)
                request = urllib2.Request(self.cicUrl+endpoint,data, {'Content-Type': 'application/json'})
                request.get_method = lambda: 'POST'

            elif ((payload is not None) or (method=="PATCH")):
                logger.debug("Preparing HTTP Patch")
                data = urllib.urlencode(payload)
                request = urllib2.Request(self.cicUrl+endpoint,data)
                request.get_method = lambda: 'PATCH'

            if xDepth:
                request.add_header("X-Depth", xDepth)

            return request

    def sendHttpRequest(self, endpoint, payload=None, method=None, xDepth=None):


            """
            CIC needs cookie handling, therefore no Basic
            authentication is used here. CIC uses the same HTTP
            code pattern as TMS therefore the below exceptions
            are thrown as they can be expected to happen
            :param: endpoint    The CIC endpoint to call(systems/
                                                        tenants)
            :param: payload     Payload defaults to None if not speci
                                fied so a GET is performed. If there is
                                payload a PATCH will be performed
            :rtype: code        Returns a 200 - OK if successful

            endpoint is in this function the path url plus parameters
            Take care to do proper url encoding before

            """

            response = None
            request = self.createHttpRequest(endpoint, payload, method, xDepth)
            opener = self.opener

            if ((payload is None) or (method == "GET")):

                logger.debug("Sending HTTP GET to "+request.get_full_url())
            else:
                if ((method is None) or (method == "PATCH")):
                    logger.debug("Sending HTTP PATCH to "+request.get_full_url())
                elif (method == "POST"):
                    logger.debug("Sending HTTP POST to "+request.get_full_url())

            try:
                response = opener.open(request)

            except urllib2.HTTPError as e:
                """Preserve error response body and put it into exception message"""
                """But do not catch specific error conditions here because the method should be generic"""

                if hasattr(e, 'read'):
                    error_message = e.read()
                    newMsg = "{:s}, Body: {}".format(e.msg,error_message)
                    newEx = urllib2.HTTPError(e.url, e.code, newMsg, e.hdrs, e.fp)
                    newEx.read = lambda: error_message
                    raise urllib2.HTTPError, newEx, sys.exc_info()[2]
                else:
                    raise


            logger.debug("Response code {}".format(response.getcode()))
            return response

            # this is only for documentation of possible TMS cases. Exceptions are not catched here, but in
            # upper level functions

            #if (e.code == 400):
            #    raise RuntimeError("Bad Request one of the provided fields contains an invalid value","TMS_BAD_REQUEST_ERR")
            #if (e.code == 401):
            #    raise RuntimeError("Logon not possible with provided TMS credentials","WRONG_CREDENTIALS_ERR")
            #if (e.code == 404):
            #    raise RuntimeError("No endpoint found under the provided url","WRONG_ENDPOINT_ERR")
            #if (e.code == 409):
            #    raise RuntimeError("Uid doesn't match the latest Uid version of the resource","UUID_VERSION_MISMATCH")
            #if (e.code == 423):
            #    raise RuntimeError("Version uid correct but resource is locked","TMS_RESOURCE_IS_LOCKED")
            #if (e.code == 500):
            #    raise RuntimeError("TMS Global-lookup inactive","TMS_GLOBAL_LOOKUP_ERR")



def _checkSystemNotFound(body):
    flag = True

    try:
        jsonDict = json.loads(body)
        message = jsonDict["details"][0]["details"]
    except (TypeError, ValueError, KeyError) as e:
        return False
    else:
        for i in range (0, len(jsonDict["details"])):
            try:
                error_mes = jsonDict["details"][i]["details"]["error"]
            except KeyError:
                continue
            else:
                return False

    return flag

