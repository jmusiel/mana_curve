import requests
import json

# Define the API endpoint
api_url = "https://json.commanderspellbook.com/variants.json"

# Make a GET request to the API
response = requests.get(api_url)

# Check if the request was successful (status code 200)
if response.status_code == 200:
    # Parse the JSON data from the response
    data = response.json()
    print("Data retrieved successfully:")
    # print(data)
    print(len(data))
    
    # Save the data to a JSON file
    with open("bulk.json", "w") as json_file:
        json.dump(data, json_file, indent=4)
    print("Data saved to variants.json")
else:
    print(f"Failed to retrieve data. Status code: {response.status_code}")