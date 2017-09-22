__all__ = ["utils"]

import datetime
import decimal
import re
import requests
import time

PRODUCT_BUSINESSPARCEL = 10001
PRODUCT_EUROBUSINESSPARCEL = 10000

class GLSException(Exception):
    pass

class LoginFailedException(GLSException):
    pass

class PhoneNumber:

    def __init__(self, *args, **kwargs):
        for k in ["country_prefix", "number"]:
            self.__dict__[k] = kwargs.get(k)

    @classmethod
    def empty(cls):
        return cls()

    @classmethod
    def parse(cls, data):
        return cls(
            country_prefix=data["countryPrefix"],
            number=data["number"]
        )

    def unparse(self):
        return {
            "countryPrefix": self.country_prefix or "",
            "number": self.number or ""
        }

class Address:

    def __init__(self, *args, **kwargs):
        for k in ["name1", "name2", "name3", "block_no1", "block_no2", "street1", "street2", "postal_code", "city", "country_code", "phone", "mobile", "email"]:
            self.__dict__[k] =  kwargs.get(k)

    def unparse(self):
        data = {
            "name1": self.name1,
            "name2": self.name2 or "",
            "name3": self.name3 or "",
            "street1": self.street1,
            "street2": self.street2 or "",
            "blockNo1": self.block_no1 or "",
            "blockNo2": self.block_no2 or "",
            "postalArea": {
                "city": self.city,
                "postalCodeDisplay": str(self.postal_code),
                "province": "",
                "countryCode": self.country_code,
                "postalCode": str(self.postal_code)
            },
            "email": self.email or "",
        }

        if self.phone:
            data["phone"] = self.phone.unparse()
        else:
            data["phone"] = PhoneNumber.empty().unparse()

        if self.mobile:
            data["mobile"] = self.mobile.unparse()
        else:
            data["mobile"] = PhoneNumber.empty().unparse()

        return data


    @classmethod
    def parse(cls, data):
        return cls(
            name1=data.get("name1") or None,
            name2=data.get("name2") or None,
            name3=data.get("name3") or None,
            street1=data.get("street1") or None,
            street2=data.get("street2") or None,
            postal_code=data["postalArea"]["postalCode"],
            city=data["postalArea"]["city"],
            country_code=data["postalArea"]["countryCode"]
        )

    @classmethod
    def parse_area(cls, data):
        return cls(
            postal_code=data["postalCode"],
            city=data["city"],
            country_code=data["countryCode"]
        )

class SenderAddress(Address):

    def __init__(self, *args, **kwargs):
        super(SenderAddress, self).__init__(*args, **kwargs)
        for k in ["address_id", "contact_id", "contact_name"]:
            self.__dict__[k] =  kwargs.get(k)

    def unparse(self):
        data = super(SenderAddress, self).unparse()

        data.update({
            "addressId": self.address_id,
            "contactId": self.contact_id,
            "contactName": self.contact_name,
        })

        return data

    @classmethod
    def parse(cls, data):
        return cls(
            name1=data.get("name1") or None,
            name2=data.get("name2") or None,
            name3=data.get("name3") or None,
            street1=data.get("street1") or None,
            street2=data.get("street2") or None,
            postal_code=data["postalArea"]["postalCode"],
            city=data["postalArea"]["city"],
            country_code=data["postalArea"]["countryCode"],
            address_id=data["addressId"],
            contact_id=data["contactId"],
            contact_name=data.get("contactName") or "",
        )

class Parcel:

    def __init__(self, *args, **kwargs):
        for k in ["tracking_number", "date", "sender", "recipient", "client", "product", "weight", "services"]:
            self.__dict__[k] = kwargs.get(k)
        self.__dict__["references"] = kwargs.get("references", [])

    @classmethod
    def parse_short(cls, data):
        parcel = cls(
            tracking_number = data.get("tuNo"),
        )
        if "date" in data:
            parcel.date=datetime.date(*[int(x) for x in data["date"].split("-")])
        if "adressInfo" in data:
            parcel.recipient = Address.parse_area(data["addressInfo"])
            parcel.recipient.name1 = data.get("consigneeName") or None
        return parcel

    @classmethod
    def parse(cls, data):
        parcel = cls(
            tracking_number=data.get("tuNo"),
            date=data.get("date")
        )
        for item in data.get("addresses", []):
            if item["type"] == "DELIVERY":
                addr_type = "recipient"
            elif item["type"] == "SHIPPER":
                addr_type = "sender"
            elif item["type"] == "REQUEST":
                addr_type = "client"
            else:
                addr_type = None
            if addr_type:
                parcel.addr_type = Address.parse(item["value"])
        for item in data.get("infos", []):
            if item["type"] == "PRODUCT":
                parcel.product = item["value"]
            elif item["type"] == "WEIGHT":
                parcel.weight = decimal.Decimal(item["value"].split(" ")[0])
            elif item["type"] == "SERVICES":
                parcel.services = item["value"].split(",")
        for item in data.get("references", []):
            if item["type"] in ("CUSTREF", "UNITNO"):
                parcel.references.append(item["value"])
        return parcel

    def __str__(self):
        desc = "%s %s" % (self.product or "Paket", self.tracking_number)
        return desc

class GLSBrowser:

    def __init__(self):
        self._sess = requests.Session()
        req = self._sess.get("https://gls-group.eu/DE/de/home")

    def _millis(self):
        return str(int(time.time() * 1000))

    def login(self, username, password):
        body = {
            "username": username,
            "password": password
        }
        req = self._sess.post("https://gls-group.eu/app/service/closed/rest/DE/de/rslg001", data=body)

        match = re.search(r"stname: \"CSRF-Token\",\s+stvalue: \"([a-f0-9]{32})\"", req.text, re.MULTILINE)
        if not match:
            raise LoginFailedException("Unable to locate CSRF token")
        self._sess.headers["Csrf-Token"] = match.group(1)

        match = re.search(r"<nav id=\"logout\">\s+([0-9A-Za-z\-_ ]+) <a ng-click=\"callLogout\(\);\">", req.text, re.MULTILINE)
        if match:
            return match.group(1)

        raise LoginFailedException()

    def get_sender_addresses(self):
        params = {
            "shipperId": "",
            "caller": "wipp003",
            "millis": self._millis()
        }
        req = self._sess.get("https://gls-group.eu/app/service/closed/rest/DE/de/rspp002", params=params)

        return [SenderAddress.parse(item) for item in req.json()["altShipperAddresses"]]

    def sender_address_id_to_address(self, address_id):
        for sender_address in self.get_sender_addresses():
            if sender_address.address_id == address_id or sender_address.contact_id == address_id:
                return sender_address

        raise ValueError("Unknown address id")

    def sender_address_id_to_contact_id(self, address_id):
        for sender_address in self.get_sender_addresses():
            if sender_address.address_id == address_id or sender_address.contact_id == address_id:
                return sender_address.contact_id

        raise ValueError("Unknown address id")

    def get_default_product(self, shipper_id, address, article_type="NORMAL"):
        params = {
            "articleType": article_type,
            "deliveryCountry": address.country_code,
            "deliveryPostalCode": str(address.postal_code),
            "shipperId": shipper_id,
            "caller": "wipp003",
            "millis": self._millis()
        }

        req = self._sess.get("https://gls-group.eu/app/service/closed/rest/DE/de/rspp003", params=params)

        for product in req.json()["products"]:
            if product["selected"] == "Y":
                return product["articleNo"]

    def get_possible_job_dates(self, shipper_id, address, product):
        params = {
            "pickupCountry": address.country_code,
            "pickupPostalCode": str(address.postal_code),
            "product": str(product),
            "shipperId": shipper_id,
            "caller": "wipp003",
        }

        req = self._sess.get("https://gls-group.eu/app/service/closed/rest/DE/de/rspp007", params=params)

        dates = []
        for item in req.json()["allowedDates"]:
            ymd = [int(x) for x in item.split("-")]
            dates.append(datetime.date(*ymd))

        return sorted(dates)

    def list_parcels(self, date_start=None, date_end=None):
        date_start = date_start or datetime.date.today()
        date_end = date_end or date_start

        params = {
            "dateForm": date_start.strftime("%Y-%m-%d"),
            "dateTo": date_end.strftime("%Y-%m-%d"),
            "caller": "witt004",
            "millis": self._millis()
        }
        req = self._sess.get("https://gls-group.eu/app/service/closed/rest/DE/de/rstt003")

        result = req.json()
        if "lastError" in result:
            if result["lastError"] == "E998":
                return []
            raise GLSException(result["exceptionText"])

        parcels = []
        for item in result["tuStatus"]:
            parcels.append(Parcel.parse_short(item))

        return parcels

    def get_parcel_details(self, tracking_number):
        params = {
            "shipperId": "",
            "caller": "witt004",
            "milis": self._millis()
        }
        req = self._sess.get("https://gls-group.eu/app/service/closed/rest/DE/de/rstt004/%s" % tracking_number, params=params)

        return Parcel.parse(req.json())

    def _references(self, references):
        if references == None:
            return []
        if isinstance(references, str):
            return [references]
        return list(references)

    def create_parcel(self, product, job_date, sender_id, sender_address_id, recipient, weight, references_shipment=None, references_parcel=None, guaranteed24=False, parcelshop_id=None):
        params = {
            "shipperId": sender_id,
            "caller": "wipp003",
            "milis": self._millis()
        }
        data = {
            "product": str(product),
            "jobDate": job_date.strftime("%Y-%m-%d"),
            "shipperId": sender_id,
            "shipperAddressId": sender_address_id,
            "consig": recipient.unparse(),
            "references": self._references(references_shipment),
            "parcels": [{
                "references": self._references(references_parcel),
                "weight": "%.2f" % weight,
            }]
        }
        if guaranteed24:
            data["services"] = ["11037"]
        if parcelshop_id:
            data["services"] = ["11055"]
            fields = data.setdefault("fields", {})
            fields["11055_altConsig_contact"] = recipient.name1
            fields["11055_parcelShopId"] = str(parcelshop_id)
            if recipient.email:
                fields["11055_altConsig_email"] = recipient.email

            phone = recipient.mobile or recipient.phone
            if phone:
                fields["11055_altConsig_mobile_prefix"] = phone.country_prefix
                fields["11055_altConsig_mobile_phone"] = phone.number
        req = self._sess.post("https://gls-group.eu/app/service/closed/rest/DE/de/rspp008", params=params, json=data)

        data = req.json()

        if not "consignementId" in data:
            raise GLSBrowser(data["exceptionText"])

        pdf = self._sess.get(data["labelUrl"]).content
        return (data["consignementId"], pdf)

    def create_return_parcel(self, shipper_id, sender, recipient, references_shipment=None, references_parcel=None):
        params = {
            "caller": "wipp006",
            "millis": self._millis(),
            "shipperId": shipper_id
        }
        data = {
            "consig": sender.unparse(),
            "parcels": [
                {
                    "references": self._references(references_parcel),
                }
            ],
            "references": self._references(references_shipment),
            "returnAddress": recipient.unparse(),
            "settings": {
                "SAVEPICKUPADDR": "N",
            },
        }

        req = self._sess.post("https://gls-group.eu/app/service/closed/rest/DE/de/rspp024", params=params, json=data)

        data = req.json()

        if not "consignmentId" in data:
            raise GLSBrowser(data["exceptionText"])

        pdf = self._sess.get(data["labelUrl"]).content
        return (data["consignmentId"], pdf)

    def cancel_parcel(self, tracking_number, job_date):
        params = {
            "caller": "wicp001",
            "milis": self._millis(),
        }
        data = {
            "parcelNos": str(tracking_number),
            "date": job_date.strftime("%Y-%m-%d"),
        }

        req = self._sess.post("https://gls-group.eu/app/service/closed/rest/DE/de/rscp002", params=params, json=data)

        if req.status_code != 200:
            try:
                data = req.json()
            except:
                pass
            else:
                if "exceptionText" in data:
                    raise GLSException("Error while deleting parcel: %s" % data["exceptionText"])
            raise GLSException("Unknown error while deleting parcel")
