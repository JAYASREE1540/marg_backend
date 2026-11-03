# MARG — setup for the live features

Three things now use real data. Two need permissions declared before they work.

## 1. Android

**`android/app/src/main/AndroidManifest.xml`** — add inside `<manifest>`, above `<application>`:

```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
```

**`android/app/build.gradle`** — geolocator needs a recent SDK:

```gradle
android {
    compileSdk 35
    defaultConfig {
        minSdk 21
        targetSdk 35
    }
}
```

## 2. iOS

**`ios/Runner/Info.plist`** — add inside the top-level `<dict>`:

```xml
<key>NSLocationWhenInUseUsageDescription</key>
<string>MARG uses your location to track your journey and warn you about hazards ahead.</string>
```

## 3. Install and run

```bash
flutter pub get
flutter run
```

---

## What's real now

| Feature | Source | Key needed |
|---|---|---|
| Map tiles | OpenStreetMap | No |
| Destination search | Nominatim | No |
| Route + distance + travel time | OSRM | No |
| Your position and speed | Device GPS via geolocator | No |
| Weather + driving advice | Open-Meteo | No |
| Place names | Nominatim reverse geocode | No |

## What's still seeded

- **Hazard reports** — there's no server yet to store them or serve other users' reports
- **Construction zones** — no free public feed exists for Indian roads; these stay hardcoded
- **Guardians** — held in memory, lost on restart
- **Speed limit** — fixed at 60 km/h in `mock_data.dart`. Real per-road limits would need OSM `maxspeed` tags, which are patchily filled in for India

## Testing on an emulator

The emulator has no real GPS. In Android Studio: **Extended controls (…) → Location**, set coordinates, then **Send**. There's also a *Routes* tab that plays back a moving journey, which is the only way to see the speed states change without driving.

On a real phone, walk around and you'll see speed update — walking pace shows as "Reduced speed" in amber, which is correct behaviour.

## Fair use

Nominatim and the OSRM demo server are free community infrastructure with rate limits (roughly one request per second). The search box is already debounced to 600 ms for this reason. Fine for a project; if this ever went live you'd self-host OSRM or move to a paid provider.
