from flask import Flask, render_template, request, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import SelectField
from geopy import Nominatim
from geopy.distance import great_circle
import pandas as pd
import folium
import requests
import math
import secrets

app = Flask(__name__)
charger_df = pd.read_csv(r'elChargers.csv')
car_icon_url = "car_icon.png"
charger_df.dropna(subset=['lat', 'lng'], inplace=True)
app.config['SECRET_KEY'] = secrets.token_hex(16)

car_icon = folium.CustomIcon(
    car_icon_url,
    icon_size=(50, 50)
)
class CarForm(FlaskForm):
    selected_car = SelectField('Select Car', choices=[])

def find_charger_on_route(start_location, end_location, car_range):
    # Make an API request to OpenRouteService for directions
    api_key = '5b3ce3597851110001cf6248ca0cba93714641c7ae90453ec91cde14'
    url = f'https://api.openrouteservice.org/v2/directions/driving-car?api_key={api_key}&start={start_location}&end={end_location}'
    response = requests.get(url)
    data = response.json()
    
    # Extract the route distance in meters and calculate in kilometers
    route_distance_meters = data['features'][0]['properties']['segments'][0]['distance']
    route_distance_kilometers = route_distance_meters / 1000
    
    # Check if the car's range is less than the route distance
    if route_distance_kilometers > car_range:
        # Find a charger that is approximately halfway along the route
        midpoint = route_distance_kilometers / 2
        total_distance = 0
        for index, charger in charger_df.iterrows():
            charger_location = (charger['lat'], charger['lng'])
            # Calculate the distance from the charger to the start and end locations
            charger_to_start = route_distance_between_points(charger_location, start_location)
            charger_to_end = route_distance_between_points(charger_location, end_location)
            # Calculate the distance from the charger to the midpoint
            charger_to_midpoint = abs(charger_to_start - midpoint)
            # If the charger is closer to the midpoint than to the start or end, use this charger
            if charger_to_midpoint < charger_to_start and charger_to_midpoint < charger_to_end:
                return charger_location
    return None

# Helper function to calculate distance between two points in kilometers
def route_distance_between_points(point1, point2):
    lat1, lon1 = point1
    lat2, lon2 = point2
    radius = 6371  # Radius of the Earth in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = radius * c
    return distance

def find_point_on_route(route_coordinates, target_distance):
    accumulated_distance = 0

    for i in range(len(route_coordinates) - 1):
        point1 = route_coordinates[i]
        point2 = route_coordinates[i + 1]
        
        # Calculate the distance between consecutive points
        segment_distance = great_circle(point1, point2).kilometers
        
        # Check if the accumulated distance has reached or exceeded the target distance
        if accumulated_distance + segment_distance >= float(target_distance):
            # Calculate the fraction of the segment to reach the target distance
            fraction = (float(target_distance) - accumulated_distance) / segment_distance
            # Interpolate the coordinates to find the point
            lat = point1[0] + fraction * (point2[0] - point1[0])
            lon = point1[1] + fraction * (point2[1] - point1[1])
            return (lat, lon)
        
        accumulated_distance += segment_distance

    # If the target distance is beyond the end of the route, return the last coordinate
    return route_coordinates[-1]

def find_closest_charger(target_point, charger_locations):
    # Initialize variables to track the closest charger and its distance
    closest_charger = None
    closest_distance = None

    for charger_location in charger_locations:
        # Calculate the distance between the target point and the charger
        distance = great_circle(target_point, charger_location).kilometers

        # Check if this charger is closer than the current closest charger
        if closest_distance is None or distance < closest_distance:
            closest_charger = charger_location
            closest_distance = distance

    return closest_charger

def geocode_location(location_name):
    geolocator = Nominatim(user_agent="your_geocoding_app_name")
    location = geolocator.geocode(location_name)
    if location:
        return location.longitude, location.latitude
    else:
        return None
    
def generate_map(start_location, end_location, car_range):
    # Load your dataset
    df = pd.read_csv(r'elChargers.csv')

    # Drop rows with missing values in lat or lng columns
    df = df.dropna(subset=['lat', 'lng'])

    # Create a base map centered around Bulgaria
    bulgaria_map = folium.Map(location=[42.7339, 25.4858], zoom_start=7)

    start_location = str(geocode_location(start_location)).strip('()')
    end_location = str(geocode_location(end_location)).strip('()')
    print(start_location)
    print(end_location)
    # Create a feature group for the chargers
    charger_group = folium.FeatureGroup(name='Chargers').add_to(bulgaria_map)
    charger_locations = []
    # Add markers for each car charger directly to the map
    for index, charger in df.iterrows():
        lat = charger['lat']
        lng = charger['lng']
        charger_locations.append((lat, lng))

        popup_content = folium.Html(f"<b>{charger['Име на локация']}</b><br>Type: {charger['AC/DC']}<br>Power: {charger['Мощност']}", script=True)

        # Choose marker color based on the type of charger
        if charger['AC/DC'] == 'DC':
            marker_color = 'orange'
        else:
            marker_color = 'green'

        folium.Marker(location=[lat, lng], popup=folium.Popup(popup_content, parse_html=True),
                      icon=folium.Icon(color=marker_color, icon="bolt", prefix="fa")).add_to(charger_group)

    # Make an API request to OpenRouteService for directions
    api_key = '5b3ce3597851110001cf6248ca0cba93714641c7ae90453ec91cde14'  # Replace with your API key
    url = f'https://api.openrouteservice.org/v2/directions/driving-car?api_key={api_key}&start={start_location}&end={end_location}'
    response = requests.get(url)
    data = response.json()
  

    # Extract the route coordinates from the response and reverse them
    route_coordinates = [(coord[1], coord[0]) for coord in data['features'][0]['geometry']['coordinates']]
    target_distance = car_range  # Replace with your desired distance in kilometers

    target_point = find_point_on_route(route_coordinates, target_distance)

    folium.Circle(location=target_point,radius=6000, fill_color='blue', fill_opacity=0.6, stroke=False).add_to(bulgaria_map)
    folium.Marker(location=target_point, icon=car_icon, icon_color = "whtie").add_to(bulgaria_map)
    if target_point:
        print(f"The point on the route at {target_distance} km is at coordinates: {target_point}")
    else:
        print("The target distance is beyond the end of the route.")
    print(car_range)
    # Extract the route distance in kilometers
    route_distance = data['features'][0]['properties']['segments'][0]['distance'] / 1000  # Convert to kilometers
    if(route_distance <= float(car_range)):
        print("Witin range")
    else:
        print("need to charge")
        closest_charger = find_closest_charger(target_point, charger_locations)

        if closest_charger:
            print(f"The closest charger is at coordinates: {closest_charger}")
        else:
            print("No chargers found.")

        folium.Circle(location=closest_charger,radius=6000, fill_color='red', fill_opacity=0.6, stroke=False, popup='Charge here').add_to(bulgaria_map)

    # Create a PolyLine to draw the route on the map
    folium.PolyLine(route_coordinates, color='blue').add_to(bulgaria_map)

    # Add a button to toggle marker visibility with a custom name for the layer control
    folium.LayerControl(collapsed=False, name='My Custom Layer Control').add_to(bulgaria_map)

    # Add a marker with a popup displaying the route distance
    distance_popup = folium.Popup(f"Route Distance: {route_distance:.2f} km")
    folium.Marker(location=route_coordinates[len(route_coordinates) // 2], popup=distance_popup).add_to(bulgaria_map)

    return bulgaria_map.get_root().render()

def get_car_options():
    # Implement logic to fetch car names from your dataset
    car_dataset = pd.read_csv(r'cardata.csv')
    car_names = car_dataset.apply(lambda row: f"{row['Brand']} {row['Model']} {row['Range_Km']}km", axis=1).tolist()
    print(car_names)
    return [(car, car) for car in car_names]

def get_car_range(selected_car):
    # Implement logic to fetch the range of the selected car from your dataset
    # You can load the car dataset and retrieve the range based on the selected car
    car_dataset = pd.read_csv(r'cardata.csv')
    selected_car_info = car_dataset[car_dataset.apply(lambda row: f"{row['Brand']} {row['Model']} {row['Range_Km']}km" == selected_car, axis=1)]
    car_range = selected_car_info['Range_Km'].values[0]
    return car_range

@app.route('/map', methods=['GET'])
def map():
    return render_template('map.html')

@app.route('/', methods=['GET', 'POST'])
def index():
    form = CarForm()
    form.selected_car.choices = get_car_options()  # Implement this function to get car names
    
    if form.validate_on_submit():
        start_location = request.form['start_location']
        end_location = request.form['end_location']
        selected_car = form.selected_car.data
        car_range = get_car_range(selected_car)  # Implement this function to get car range
        # Other form handling logic
        map_html = generate_map(start_location, end_location, car_range)

        # Pass the HTML string to the template
        return render_template('index.html', form=form, map_html=map_html)
    
    return render_template('index.html', form=form)

if __name__ == '__main__':
    app.run(debug=True)