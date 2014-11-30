import collections
import datetime
import decimal
import json
import re
import requests
import time

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
            data["mobile"] = mobile.unparse()
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

class Parcel:

    def __init__(self, *args, **kwargs):
        for k in ["tracking_number", "date", "sender", "recipient", "client", "product", "weight"]:
            self.__dict__[k] = kwargs.get(k)

    @classmethod
    def parse_short(cls, data):
        parcel = cls(
            tracking_number = data.get("tuNo"),
            date=datetime.date(*[int(x) for x in data["date"].split("-")])
        )
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
        match = re.search(r"<li class=\"user\">(.*?)</li>", req.text)
        if match:
            return match.group(1)
        raise LoginFailedException()

    def list_senders(self):
        params = {
            "shipperId": "",
            "caller": "wipp003",
            "millis": self._millis()
        }
        req = self._sess.get("https://gls-group.eu/app/service/closed/rest/DE/de/rspp002", params=params)

        senders = {}
        for item in req.json()["altShipperAddresses"]:
            senders[item["contactId"]] = Address.parse(item)

        return senders

    def get_possible_job_dates(self, product, address):
        params = {
            "pickupCountry": address.country_code,
            "pickupPostalCode": str(address.postal_code),
            "product": str(product),
            "shipperId": "",
            "caller": "wipp003",
            "millis": self._millis()
        }

        req = self._sess.get("https://gls-group.eu/app/service/closed/rest/DE/de/rspp007", params=params)

        dates = []
        for item in req.json()["allowedDates"]:
            ymd = [int(x) for x in item.split("-")]
            dates.append(datetime.date(*ymd))

        return sorted(dates)

    def list_parcels(self, date_start=None, date_end=None, include_cancelled=False):
        date_start = date_start or datetime.date.today()
        date_end = date_end or date_start

        params = {
            "dateForm": date_start.strftime("%Y-%m-%d"),
            "dateTo": date_end.strftime("%Y-%m-%d"),
            "caller": "witt004",
            "millis": self._millis()
        }
        req = self._sess.get("https://gls-group.eu/app/service/closed/rest/DE/de/rstt003")

        parcels = []
        for item in req.json()["tuStatus"]:
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

    def create_parcel(self, product, job_date, sender_id, sender_address_id, recipient, weight):
        headers = {
            "Content-Type": "application/json"
        }
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
            "references": [""],
            "parcels": [{
                "references": [""],
                "weight": "%.2g" % weight
            }]
        }

        req = self._sess.post("https://gls-group.eu/app/service/closed/rest/DE/de/rspp008", headers=headers, params=params, data=json.dumps(data))

        data = req.json()
        if "consignementId" in data:
            pdf = self._sess.get(data["labelUrl"]).content
        return (data["consignementId"], pdf)
