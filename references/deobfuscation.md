# Deobfuscation Reference

## Android — ProGuard / R8

### Retrieve mapping file
Mapping files must be stored in your artifact store keyed by `{app_version}_{build_number}`.
Recommended storage: Nexus, Artifactory, or S3 with path pattern:
```
s3://your-bucket/mappings/android/{app_version}/{build_number}/mapping.txt
```

### Retrace command
```bash
# Using proguard retrace
java -jar retrace.jar mapping.txt stacktrace.txt

# Using bundled retrace (newer builds)
java -cp r8.jar com.android.tools.r8.retrace.Retrace mapping.txt stacktrace.txt
```

### Frame filtering — exclude these packages
```
android.*
androidx.*
com.google.*
kotlin.*
kotlinx.*
okhttp3.*
retrofit2.*
com.squareup.*
io.reactivex.*
java.*
javax.*
sun.*
```
Keep only frames matching your org's package namespace, e.g. `com.yourbank.*`

---

## iOS — dSYM

### Retrieve dSYM
Store dSYM bundles in your artifact store:
```
s3://your-bucket/dsyms/ios/{app_version}/{build_number}/{BundleID}.app.dSYM.zip
```

### Symbolicate command
```bash
# Single address
atos -arch arm64 -o YourApp.app.dSYM/Contents/Resources/DWARF/YourApp \
  -l 0x{load_address} 0x{crash_address}

# Full crash log
symbolicatecrash crash.ips YourApp.app.dSYM > symbolicated.txt
```

### Frame filtering — exclude these frameworks
```
UIKit
Foundation
CoreFoundation
libsystem_*
libobjc*
CoreData
CFNetwork
Security
```

---

## React Native

### Retrieve source map
```
s3://your-bucket/sourcemaps/rn/{app_version}/{build_number}/main.jsbundle.map
```

### Resolve frames
```bash
npx source-map resolve main.jsbundle.map {line} {column}
```

### Frame filtering
Exclude:
```
node_modules/react-native/*
node_modules/react/*
node_modules/@react-navigation/*
hermes/*
```

---

## Mapping file missing — escalation path

1. Create a `[TRIAGE BLOCKED]` ticket immediately
2. Assign to the release/build engineer
3. Add label: `mapping-file-missing`
4. Include: app_version, build_number, platform, date of crash
5. Link the AppDynamics crash group URL
6. Do not attempt attribution from an obfuscated trace
