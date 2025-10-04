import tkinter as tk
from tkinter import messagebox
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import geopandas as gpd
from shapely.geometry import Point
import requests
import threading

# ----------------- AIR QUALITY API CONFIG -----------------
API_KEY = "6c913facf9a446b0aaf80d3a774901a1"  # Replace with your OpenWeather API key
BASE_URL = "https://api.openweathermap.org/data/2.5/air_pollution"


def get_air_quality(lat, lon):
    """Fetch air quality data from OpenWeather API."""
    try:
        url = f"{BASE_URL}?lat={lat}&lon={lon}&appid={API_KEY}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "list" not in data or not data["list"]:
            return {"aqi": 0, "components": {}}
        info = data["list"][0]
        aqi = info["main"]["aqi"]
        components = info["components"]
        return {"aqi": aqi, "components": components}
    except Exception as e:
        return {"error": str(e)}


# ----------------- NASA EONET API -----------------
def get_nasa_events():
    """Fetch all active events from NASA EONET."""
    url = "https://eonet.gsfc.nasa.gov/api/v2.1/events?status=open"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data['events']
    except Exception as e:
        print("Error fetching NASA EONET data:", e)
        return []


nasa_events = get_nasa_events()

# -----------------------------LLM (Using FREE OpenRouter API)-----------------------
OPENROUTER_API_KEY = "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"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
FREE_MODEL = "mistralai/mistral-7b-instruct:free"


def ask_llm(aq_data):
    """Send air quality data to OpenRouter and get a child-friendly summary."""
    if "error" in aq_data:
        return f"Error fetching AQI: {aq_data['error']}"

    aqi = aq_data.get("aqi", 0)
    components = aq_data.get("components", {})

    llm_prompt = f"Air Quality Score (1=Good, 5=Poor): {aqi}\nPollutants (μg/m³):\n"
    for k, v in components.items():
        llm_prompt += f"{k}: {v}\n"

    llm_prompt += """
Task: Summarize this air quality data in a simple, fun way
that a child can understand. Use emojis and simple words.
Explain if the air is good or bad and which pollutant is highest.
Keep it under 50 word without any emojy  also make  easy  for kid to understand and indcat if it is harmful for asmha .

"""

    print("\n--- LLM Prompt ---")
    print(llm_prompt)
    print("------------------\n")

    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": FREE_MODEL,
            "messages": [{"role": "user", "content": llm_prompt}]
        }
        res = requests.post(OPENROUTER_API_URL, headers=headers, json=data, timeout=30)
        res.raise_for_status()
        summary = res.json()["choices"][0]["message"]["content"]
        return summary
    except Exception as e:
        return f"Error calling LLM: {e}"


def ask_llm_thread(aq_data, lat=None, lon=None):
    """Run ask_llm in a separate thread and show styled popup."""
    def worker():
        try:
            summary = ask_llm(aq_data)
            print("\n✨ Kid-friendly summary:\n", summary)

            # Run GUI code in main thread
            def show_popup():
                popup = tk.Toplevel(root)
                popup.title("AI Air Quality Summary")
                popup.geometry("500x300")
                popup.resizable(True, True)

                # Text widget for better styling
                text_widget = tk.Text(popup, wrap=tk.WORD, font=("Helvetica", 14), bg="#f0f0f0")
                text_widget.insert(tk.END, summary)
                text_widget.config(state=tk.DISABLED)  # Make read-only
                text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

                # Close button
                tk.Button(popup, text="Close", command=popup.destroy, font=("Helvetica", 12)).pack(pady=5)

            root.after(0, show_popup)

        except Exception as e:
            print("⚠️ Thread error:", e)

    threading.Thread(target=worker, daemon=True).start()


# ----------------- LOAD WORLD GEOJSON -----------------
url = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
world = gpd.read_file(url)
country_column = next((col for col in world.columns if col != 'geometry'), None)
if country_column is None:
    raise ValueError("No valid country name column found in the GeoJSON")
print("Using country column:", country_column)

selected_countries = []
country_aqi = {}

# ----------------- TKINTER WINDOW -----------------
root = tk.Tk()
root.title("Air Quality + NASA Events Map")
root.geometry("1200x800")

fig = plt.Figure(figsize=(12, 8))
ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.draw()
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


# ----------------- AQI COLOR MAPPING -----------------
def aqi_to_color(aqi):
    if aqi == 1:
        return "green"
    elif aqi == 2:
        return "yellow"
    elif aqi == 3:
        return "orange"
    elif aqi == 4:
        return "red"
    elif aqi == 5:
        return "purple"
    return "white"


# ----------------- EVENT CATEGORY COLORS -----------------
event_colors = {
    "Wildfires": "red",
    "Severe Storms": "blue",
    "Volcanoes": "orange",
    "Sea and Lake Ice": "cyan",
    "Floods": "green",
    "Earthquakes": "purple",
    "Landslides": "brown",
    "Other": "pink"
}


# ----------------- REDRAW MAP -----------------
def redraw_map():
    ax.clear()
    ax.set_facecolor("white")
    ax.add_feature(cfeature.BORDERS, edgecolor='black', linewidth=1)
    ax.add_feature(cfeature.OCEAN, facecolor='lightblue')

    for idx, row in world.iterrows():
        country_name = row[country_column]
        color = aqi_to_color(country_aqi.get(country_name, 0))
        ax.add_geometries([row['geometry']], ccrs.PlateCarree(),
                          facecolor=color, edgecolor='black')

    for event in nasa_events:
        if 'geometry' not in event or not event['geometry']:
            continue
        cat_name = event['categories'][0]['title'] if event['categories'] else "Other"
        color = event_colors.get(cat_name, "black")
        for geom in event['geometry']:
            if 'coordinates' not in geom:
                continue
            lon, lat = geom['coordinates']
            ax.plot(lon, lat, marker='o', color=color, markersize=6, transform=ccrs.PlateCarree())

    gl = ax.gridlines(draw_labels=True, linewidth=0.5, color='gray', alpha=0.5, linestyle='--')
    gl.top_labels = False
    gl.right_labels = False
    canvas.draw()


# ----------------- SCROLL ZOOM -----------------
def on_scroll(event):
    base_scale = 1.5
    cur_xlim = ax.get_xlim()
    cur_ylim = ax.get_ylim()
    xdata = event.xdata
    ydata = event.ydata
    if xdata is None or ydata is None:
        return

    scale_factor = 1 / base_scale if event.button == 'up' else base_scale
    new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
    new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

    ax.set_xlim([xdata - new_width * (xdata - cur_xlim[0]) / (cur_xlim[1] - cur_xlim[0]),
                 xdata + new_width * (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])])
    ax.set_ylim([ydata - new_height * (ydata - cur_ylim[0]) / (cur_ylim[1] - cur_ylim[0]),
                 ydata + new_height * (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])])
    canvas.draw()


# ----------------- HANDLE CLICKS -----------------
def on_click(event):
    if event.inaxes:
        lon, lat = event.xdata, event.ydata
        clicked_point = Point(lon, lat)

        for idx, row in world.iterrows():
            if row['geometry'].contains(clicked_point):
                country_name = row[country_column]
                if country_name in selected_countries:
                    selected_countries.remove(country_name)
                    country_aqi.pop(country_name, None)
                    print(f"{country_name} deselected!")
                else:
                    selected_countries.append(country_name)
                    aq_data = get_air_quality(lat, lon)
                    if "error" in aq_data:
                        print(f"Error fetching AQI for {country_name}: {aq_data['error']}")
                        country_aqi[country_name] = 0
                    else:
                        country_aqi[country_name] = aq_data["aqi"]
                        pollutants_str = "\n".join([f"{k}: {v}" for k, v in aq_data["components"].items()])
                        print(f"\n{'=' * 50}")
                        print(f"🌍 {country_name} selected!")
                        print(f"AQI (1=Good, 5=Poor): {aq_data['aqi']}")
                        print(f"Pollutants (μg/m³):\n{pollutants_str}")
                        ask_llm_thread(aq_data, lat, lon)
                redraw_map()
                return

        for event_n in nasa_events:
            if 'geometry' not in event_n or not event_n['geometry']:
                continue
            for geom in event_n['geometry']:
                if 'coordinates' not in geom:
                    continue
                ev_lon, ev_lat = geom['coordinates']
                if abs(lon - ev_lon) < 1 and abs(lat - ev_lat) < 1:
                    cat_name = event_n['categories'][0]['title'] if event_n['categories'] else "Other"
                    print(f"\n{'=' * 50}")
                    print(f"🛰️ NASA Event Detected:")
                    print(f"Title: {event_n['title']}")
                    print(f"Category: {cat_name}")
                    print(f"Coordinates: Lat {ev_lat:.2f}, Lon {ev_lon:.2f}")
                    print('=' * 50)
                    return

        aq_data = get_air_quality(lat, lon)
        if "error" not in aq_data:
            pollutants_str = "\n".join([f"{k}: {v}" for k, v in aq_data["components"].items()])
            print(f"\n{'=' * 50}")
            print(f"📍 Coordinates: Lat {lat:.2f}, Lon {lon:.2f}")
            print(f"AQI (1=Good, 5=Poor): {aq_data['aqi']}")
            print(f"Pollutants (μg/m³):\n{pollutants_str}")
            ask_llm_thread(aq_data, lat, lon)


# ----------------- INITIAL DRAW -----------------
redraw_map()
fig.canvas.mpl_connect("button_press_event", on_click)
fig.canvas.mpl_connect("scroll_event", on_scroll)

try:
    root.mainloop()
except Exception as e:
    print("🔥 Tkinter crashed:", e)
