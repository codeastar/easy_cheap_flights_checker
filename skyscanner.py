import requests
import os, sys, json
from datetime import date, timedelta, datetime
from tinydb import TinyDB, Query

db = TinyDB('skyscanner.json')
Profile = db.table('Profile')
Place = db.table('Place')

ENDPOINT_PREFIX = "https://skyscanner-skyscanner-flight-search-v1.p.rapidapi.com/apiservices/"
TAG = "Return \\ Depart"
END_TAG = " | "
CELL_LENGTH = int(len(TAG))

def initProfileDB():
  if "SKYSCAN_RAPID_API_KEY" in os.environ:
    API_KEY = os.environ['SKYSCAN_RAPID_API_KEY']   
    Profile.upsert({'api_key':API_KEY}, Query().api_key.exists())
  else: 
    API_KEY = Profile.search(Query().api_key)
    if API_KEY == []: 
      sys.exit("No API key found")
    API_KEY = API_KEY[0]['api_key']

  init_market = "US" if Profile.search(Query().market)==[] else Profile.search(Query().market)[0]['market']
  init_from = "SFO" if Profile.search(Query().place_from)==[] else Profile.search(Query().place_from)[0]['place_from']
  init_to = "JFK" if Profile.search(Query().place_to)==[] else Profile.search(Query().place_to)[0]['place_to']
  init_connect = "Y" if Profile.search(Query().connect)==[] else Profile.search(Query().connect)[0]['connect']
  init_currency = "USD" if Profile.search(Query().currency)==[] else Profile.search(Query().currency)[0]['currency']
  init_depart = (date.today() + timedelta(days=7)).strftime('%Y-%m-%d') if (Profile.search(Query().date_depart)==[] or (date.today() > datetime.strptime(Profile.search(Query().date_depart)[0]['date_depart'], '%Y-%m-%d').date())) else Profile.search(Query().date_depart)[0]['date_depart']
  init_return = (date.today() + timedelta(days=11)).strftime('%Y-%m-%d') if (Profile.search(Query().date_return)==[] or (date.today() > datetime.strptime(Profile.search(Query().date_return)[0]['date_return'], '%Y-%m-%d').date())) else Profile.search(Query().date_return)[0]['date_return']

  profile_dict = {
    "API_KEY": API_KEY,
    "init_market": init_market,
    "init_from": init_from, 
    "init_to": init_to,
    "init_connect": init_connect,
    "init_currency": init_currency,
    "init_depart": init_depart,
    "init_return": init_return,
  }
  return profile_dict

def handleAPIException(responseText, apiname):
      print(json.dumps(json.loads(responseText), indent=3, sort_keys=True))
      sys.exit(f"API exception on [{apiname}]")

def getIataCodeByString(place_string, market, currency, headers):
    place_info = Place.search(Query()['search_string'] == place_string)  #search from DB first
    if place_info == []:
        print("Searching IATA code from Skyscanner...")    #search from Skyscanner API
        url = ENDPOINT_PREFIX+f"autosuggest/v1.0/{market}/{currency}/en-US/"
        querystring = {"query":place_string}
        response = requests.request("GET", url, headers=headers, params=querystring)
        if response.status_code != 200: handleAPIException(response.text, getIataCodeByString.__name__)
        place_json = json.loads(response.text)
        for place in place_json["Places"]:
            if len(place['PlaceId']) == 7:
                Place.upsert({'search_string':place_string, 'iata':place['PlaceId'][:3], 'name':place['PlaceName'], 'country':place['CountryName']}, Query().api_key.exists())
                iata_code = place['PlaceId'][:3]
                break
    else: 
       iata_code =  place_info[0]["iata"]   #get the code from DB
    return iata_code

def getCheapQuote(market, currency, place_from, place_to, date_depart, date_return, check_place):    
    url = ENDPOINT_PREFIX+f"browsequotes/v1.0/{market}/{currency}/en-US/{place_from}/{place_to}/{date_depart}/{date_return}"
    response = requests.request("GET", url, headers=headers)
    if response.status_code != 200: handleAPIException(response.text, "browse quotes")
    quotes_json = json.loads(response.text)
    min_price_low = None
    carrier_names = []
    is_direct = "N/A"
    for quote in quotes_json["Quotes"]:
        direct_flight = quote['Direct']
        if (connect==False and direct_flight==False): continue
        min_price_this = quote['MinPrice']     
        if (min_price_low == None or min_price_this < min_price_low):  
            min_price_low = min_price_this
            is_direct = direct_flight
            carrier_id_outbound = quote['OutboundLeg']['CarrierIds']
            carrier_id_inbound = quote['InboundLeg']['CarrierIds']
            carrier_ids = set(carrier_id_outbound + carrier_id_inbound)

    if min_price_low != None: 
        for carrier in quotes_json["Carriers"]:
          carrier_id = carrier['CarrierId']
          if carrier_id in carrier_ids:
            carrier_name = carrier['Name']
            carrier_names.append(carrier_name)
            if len(carrier_names) == len(carrier_ids): break
        if (check_place):    
          for place in quotes_json["Places"]:     
            iata_code = place['IataCode']
            if (iata_code == place_from): 
              place_from = f"{place_from} - {place['Name']}, {place['CityName']}, {place['CountryName']}"
            elif (iata_code == place_to): 
              place_to = f"{place_to} - {place['Name']}, {place['CityName']}, {place['CountryName']}"

    cheapquote_dict = {
      "price": min_price_low,
      "carriers": carrier_names,
      "is_direct": is_direct,
      "place_from": place_from, 
      "place_to": place_to
    }         
    return cheapquote_dict

def displayPrice(cheapquote_dict, display_index):
  if (cheapquote_dict['price'] == None):
    display_msg="No info found"
  elif display_index==0:
    display_msg=f"{currency} {cheapquote_dict['price']}"
  elif display_index==1:
    display_msg=f"{cheapquote_dict['carriers']}"
    display_msg = display_msg.replace("[", "").replace("]", "").replace("'", "")
    display_msg = (display_msg[:CELL_LENGTH-2] + '..') if (len(display_msg) > CELL_LENGTH) else display_msg           
  elif display_index==2:
    display_msg=f"Direct? {'Y' if (cheapquote_dict['is_direct']) else 'N'}"     
  print(f"{display_msg}{' '*(CELL_LENGTH-len(display_msg))}", end=END_TAG)

profile_dict = initProfileDB()  #init our profile
headers = {
    'x-rapidapi-host': "skyscanner-skyscanner-flight-search-v1.p.rapidapi.com",
    'x-rapidapi-key': profile_dict["API_KEY"]
    }

market= input(f"Market Country(ISO two-letter country code) [{profile_dict['init_market']}]: ").upper() or profile_dict['init_market']
place_from = input(f"From(place name or IATA code) [{profile_dict['init_from']}]: ") or profile_dict['init_from']
place_to = input(f"To(place name or IATA code) [{profile_dict['init_to']}]: ") or profile_dict['init_to'] 
connect = input(f"Consider Connecting Flight(Y/N) [{profile_dict['init_connect']}]: ") or profile_dict['init_connect']
currency = input(f"Currency [{profile_dict['init_currency']}]: ").upper() or profile_dict['init_currency']
date_depart = input(f"Depart (YYYY-MM-DD) [{profile_dict['init_depart']}]: ") or profile_dict['init_depart']
date_return = input(f"Return (YYYY-MM-DD) [{profile_dict['init_return']}]: ") or profile_dict['init_return']

place_from = getIataCodeByString(place_from, market, currency, headers) if (len(place_from) > 3) else place_from  
place_to = getIataCodeByString(place_to, market, currency, headers) if (len(place_to) > 3) else place_to  
connect = True if (connect.lower() == "y" or connect.lower() == "yes") else False  

print("Start processing your request...")
selected_cheapquote_dict = getCheapQuote(market, currency, place_from, place_to, date_depart, date_return, True)
print(f"\nFrom: {selected_cheapquote_dict['place_from']}")
print(f"To: {selected_cheapquote_dict['place_to']}")
print(f"Depart: {date_depart}")
print(f"Return: {date_return}")
print(f"Consider Connecting Fligh? {'Y' if (connect) else 'N'}")

Profile.upsert({'market':market}, Query().init_market.exists()) #save a savepoint
Profile.upsert({'place_from':place_from}, Query().place_from.exists())
Profile.upsert({'place_to':place_to}, Query().place_to.exists())
Profile.upsert({'connect': ("Y" if (connect) else "N")}, Query().connect.exists())
Profile.upsert({'currency':currency}, Query().currency.exists())
Profile.upsert({'date_depart':date_depart}, Query().date_depart.exists())
Profile.upsert({'date_return':date_return}, Query().date_return.exists())

dates_depart = []
dates_return = []
selected_date_depart = date_depart
selected_date_return = date_return
dates_depart.append(date_depart)
dates_return.append(date_return)

for change_day_minus in range(3): #do last 3 days search
  date_depart_d_obj = datetime.strptime(date_depart, '%Y-%m-%d').date()
  if (date_depart_d_obj > date.today()):
    date_depart = (date_depart_d_obj - timedelta(days=1)).strftime('%Y-%m-%d')
    date_return = (datetime.strptime(date_return, '%Y-%m-%d').date() - timedelta(days=1)).strftime('%Y-%m-%d')
    dates_depart.insert(0,date_depart)
    dates_return.insert(0,date_return)
  else: 
    break

date_depart = selected_date_depart
date_return = selected_date_return
for change_day_plus in range(3):  #do next 3 days search
  date_depart = (datetime.strptime(date_depart, '%Y-%m-%d').date() + timedelta(days=1)).strftime('%Y-%m-%d')
  date_return = (datetime.strptime(date_return, '%Y-%m-%d').date() + timedelta(days=1)).strftime('%Y-%m-%d')
  dates_depart.append(date_depart)
  dates_return.append(date_return)

dates_return.insert(0,TAG)
row_length = 0
for row_index, row_cell in enumerate(dates_return):
  row_cell = row_cell+"*" if (row_cell == selected_date_return) else row_cell
  print(f"\n{row_cell}{' '*(len(TAG)-len(row_cell))}", end =END_TAG)
  if row_index==0:
     for col_cell in dates_depart:
       col_cell = col_cell+"*" if (col_cell == selected_date_depart) else col_cell
       print(f"{col_cell}{' '*(CELL_LENGTH-len(col_cell))}", end=END_TAG)
       row_length += CELL_LENGTH+len(END_TAG)
     print(f"\n{'-'*(len(TAG))}{END_TAG}{'-'*row_length}", end ="")
  else: 
     cheapquotes = []
     for col_cell in dates_depart:
       if (row_cell[:10]==selected_date_return and col_cell==selected_date_depart):
         cheapquote_dict = selected_cheapquote_dict
       elif (datetime.strptime(col_cell, '%Y-%m-%d').date() < datetime.strptime(row_cell[:10], '%Y-%m-%d').date()):
         cheapquote_dict = getCheapQuote(market, currency, place_from, place_to, col_cell, row_cell[:10], False)
       else: 
         cheapquote_dict = { "price": None }
       cheapquotes.append(cheapquote_dict)
       displayPrice(cheapquote_dict, 0)
     
     for i in range(1,3):
       print(f"\n{' '*(len(TAG))}", end =END_TAG)
       for cheapquote in cheapquotes:
         displayPrice(cheapquote, i)   
     print(f"\n{'-'*(len(TAG))}{END_TAG}{'-'*row_length}", end ="")