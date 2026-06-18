"""
Compact intShopping response payload.

Removes noisy fields, keeps decision-critical data, limits groupList to top N.

Usage:
    python compact_intl_payload.py raw_result.json --limit 10
    python compact_intl_payload.py raw_result.json --limit 5 --output compact.json
"""
import json
import sys


PRICE_KEEP_FIELDS = {
    "priceId", "airId", "officeId", "supplier", "source",
    "price", "tax", "addPrice", "servicePrice", "totalPrice",
    "customersId", "passengerType", "allowTicket", "specialRate",
    "selfBigCustomersId",
}

TRIP_KEEP_FIELDS_FLIGHT = {
    "id", "uniqueId", "flightId", "operatingFlightId",
    "airLine", "flyDate", "arrDate", "duration", "mile",
    "meal", "type", "fromPort", "toPort", "stopList",
}

TRIP_KEEP_FIELDS_TRIP = {
    "id", "airLine", "duration", "mile", "virtualInd",
}

CAB_KEEP_FIELDS = {
    "id", "flightId", "airLine", "cab", "num", "cabClass",
    "carryBaggageId", "checkBaggageId",
}

BAGGAGE_KEEP_FIELDS = {
    "id", "baggageType", "pieces", "weight", "totalWeight",
    "textCh",
}

RULE_KEEP_FIELDS = {
    "refund", "change", "upgra",
}

CITY_KEEP_FIELDS = {
    "cityCode", "cityName", "airPortName",
}

AIRWAY_KEEP_FIELDS = {
    "companyNo", "companyName",
}

ADD_SERVICE_KEEP = {
    "serviceType", "serviceName", "tagTypeCn",
}


def compact_group(group: dict) -> dict:
    result = {"groupId": group.get("groupId", "")}

    trips = []
    for trip in group.get("tripList", []):
        compact_trip = {k: trip.get(k) for k in TRIP_KEEP_FIELDS_TRIP if k in trip}
        flights = []
        for fl in trip.get("flightList", []):
            compact_fl = {k: fl.get(k) for k in TRIP_KEEP_FIELDS_FLIGHT if k in fl}
            stops = fl.get("stopList", [])
            if stops:
                compact_fl["stopList"] = [{"stopPort": s.get("stopPort"), "stopTime": s.get("stopTime")} for s in stops]
            visa_info = trip.get("visaInfoList", [])
            if visa_info:
                compact_fl["visaInfoList"] = [{"visaType": v.get("visaType"), "isVisaNeeded": v.get("isVisaNeeded"), "country": v.get("country")} for v in visa_info]
            flights.append(compact_fl)
        compact_trip["flightList"] = flights
        trips.append(compact_trip)
    result["tripList"] = trips

    prices = []
    for price in group.get("priceList", []):
        compact_price = {k: price.get(k) for k in PRICE_KEEP_FIELDS if k in price}
        rule_list = price.get("ruleList", [])
        if rule_list:
            compact_price["ruleList_count"] = len(rule_list)
            compact_price["ruleList_hasBigCustomer"] = any(r.get("enterpriseId") for r in rule_list)
        trip_prices = []
        for tp in price.get("tripList", []):
            compact_tp = {
                "airLine": tp.get("airLine"),
                "caption": tp.get("caption"),
                "cabClass": tp.get("cabClass"),
                "io": tp.get("io"),
                "fareBasisCode": tp.get("fareBasisCode"),
            }
            rule = tp.get("rule", {})
            if rule:
                compact_tp["rule"] = {k: rule.get(k) for k in RULE_KEEP_FIELDS if k in rule}
            cabs = tp.get("cabList", [])
            if cabs:
                compact_tp["cabList"] = [{k: c.get(k) for k in CAB_KEEP_FIELDS if k in c} for c in cabs]
            add_services = tp.get("addServiceList", [])
            if add_services:
                compact_tp["addServiceList"] = [{k: s.get(k) for k in ADD_SERVICE_KEEP if k in s} for s in add_services]
            trip_prices.append(compact_tp)
        compact_price["tripList"] = trip_prices
        prices.append(compact_price)
    result["priceList"] = prices

    return result


def compact_payload(raw: dict, limit: int = 10) -> dict:
    data = raw.get("data", {})
    result = {"serialNumber": data.get("serialNumber", "")}

    groups = data.get("groupList", [])
    result["groupCount"] = len(groups)
    result["groupList"] = [compact_group(g) for g in groups[:limit]]

    baggage = data.get("baggageList", [])
    if baggage:
        result["baggageList"] = [{k: b.get(k) for k in BAGGAGE_KEEP_FIELDS if k in b} for b in baggage]

    cities = data.get("cityList", [])
    if cities:
        result["cityList"] = [{k: c.get(k) for k in CITY_KEEP_FIELDS if k in c} for c in cities]

    airways = data.get("airwayList", [])
    if airways:
        result["airwayList"] = [{k: a.get(k) for k in AIRWAY_KEEP_FIELDS if k in a} for a in airways]

    raw_error = raw.get("errorCode", "0")
    if str(raw_error) != "0":
        result["errorCode"] = raw_error
        result["errorMsg"] = raw.get("errorMsg", "")

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python compact_intl_payload.py <raw.json> [--limit N] [--output out.json]")
        sys.exit(1)

    limit = 10
    out_path = None
    args = sys.argv[1:]
    i = 1
    while i < len(args):
        if args[i] == "--limit":
            i += 1
            limit = int(args[i])
        elif args[i] == "--output":
            i += 1
            out_path = args[i]
        i += 1

    with open(sys.argv[1], encoding="utf-8") as f:
        raw = json.load(f)

    result = compact_payload(raw, limit)
    output = json.dumps(result, ensure_ascii=False, indent=2)

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
