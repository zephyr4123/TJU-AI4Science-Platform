# LaminDB Setup & Deployment

This document covers installation, configuration, instance management, storage options, and deployment strategies for LaminDB.

## Installation

### Basic Installation

```bash
# Install the current validated baseline
uv pip install 'lamindb==2.5.1'

# Minimal namespace-only package for lightweight clients
uv pip install 'lamindb-core==2.5.1'
```

### Installation with Extras

Install optional dependencies for specific functionality:

```bash
# Google Cloud Platform support
uv pip install 'lamindb[gcp]==2.5.1'

# Flow cytometry formats
uv pip install 'lamindb[fcs]==2.5.1'

# Array storage and streaming (Zarr v2 support)
uv pip install 'lamindb[zarr-v2]==2.5.1'

# AWS S3 support (usually included by default)
uv pip install 'lamindb==2.5.1'

# Multiple extras
uv pip install 'lamindb[gcp,zarr-v2,fcs]==2.5.1'
```

### Module Plugins

```bash
# Biological ontologies (Bionty)
uv pip install 'bionty==2.4.0'

# Wet lab functionality
uv pip install 'lamindb-wetlab==<reviewed-version>'

# Clinical schemas, such as clinicore or OMOP-focused modules
uv pip install '<clinical-module>==<reviewed-version>'
```

Use a project lock file for production deployments. The pinned LaminDB and Bionty versions above reflect the current refresh baseline; for optional modules, look up the current official package and pin the reviewed version rather than installing a floating latest release.

### Verify Installation

```python
import lamindb as ln
print(ln.__version__)

# Check available modules
import bionty as bt
print(bt.__version__)
```

## Instance Initialization

### Local SQLite Instance

For local development and small datasets:

```bash
# Initialize in current directory
lamin init --storage ./mydata

# Initialize in specific directory
lamin init --storage /path/to/data

# Initialize with specific modules
lamin init --storage ./mydata --modules bionty

# Initialize with multiple modules
lamin init --storage ./mydata --modules bionty,wetlab
```

### Instance Naming

```bash
# Specify instance name
lamin init --storage ./mydata --name my-project

# Default name uses directory name
lamin init --storage ./mydata  # Instance name: "mydata"
```

## Connecting to Instances

### Connect to Your Own Instance

```bash
# By name
lamin connect my-project
```

### Switching Between Instances

```bash
# List available instances
lamin info

# Switch instance
lamin connect another-instance

# Close current instance
lamin close
```

## Storage Configuration

### Local Storage

**Advantages:**
- Fast access
- No internet required
- Simple setup

**Setup:**
```bash
lamin init --storage ./data
```

## Database Configuration

### SQLite (Default)

**Advantages:**
- No separate database server
- Simple setup
- Good for development

**Limitations:**
- Not suitable for concurrent writes
- Limited scalability

**Setup:**
```bash
# SQLite is default
lamin init --storage ./data
# Database stored at ./data/.lamindb/
```

### Database Schema Management

```bash
# Check current schema version
lamin migrate check

# Upgrade schema
lamin migrate deploy

# View migration history
lamin migrate history
```

## Cache Configuration

### Cache Directory

LaminDB maintains a local cache for cloud files:

```python
import lamindb as ln

# View cache location
print(ln.settings.cache_dir)
```

### Configure Cache Location

```bash
# Set cache directory
lamin cache set /path/to/cache

# View current cache settings
lamin cache get
```

### System-Wide Cache (Multi-User)

For shared systems with multiple users:

```bash
# Create system settings file
sudo mkdir -p /system/settings
sudo nano /system/settings/system.env
```

Add to `system.env`:
```bash
lamindb_cache_path=/shared/cache/lamindb
```

Ensure permissions:
```bash
sudo chmod 755 /shared/cache/lamindb
sudo chown -R shared-user:shared-group /shared/cache/lamindb
```

### Cache Management

```python
import lamindb as ln

# Clear cache for specific artifact
artifact = ln.Artifact.get(key="data.h5ad")
artifact.delete_cache()

# Check if artifact is cached
if artifact.is_cached():
    print("Already cached")

# Manually clear entire cache
import shutil
shutil.rmtree(ln.settings.cache_dir)
```

## Settings Management

### View Current Settings

```python
import lamindb as ln

# User settings
print(ln.setup.settings.user)
# User(handle='username', email='user@email.com', name='Full Name')

# Instance settings
print(ln.setup.settings.instance)
# Instance(name='my-project', storage='s3://bucket/path')
```

### Configure Settings

```bash
# Set development directory for relative keys
lamin settings set dev-dir /path/to/project

# Configure git sync
lamin settings set sync-git-repo https://github.com/user/repo.git

# View all settings
lamin settings
```

### Environment Variables

```bash
# Cache directory
export LAMIN_CACHE_DIR=/path/to/cache

# Settings directory
export LAMIN_SETTINGS_DIR=/path/to/settings

# Git sync
export LAMINDB_SYNC_GIT_REPO=https://github.com/user/repo.git

```

## Instance Management

### Viewing Instance Information

```bash
# Current instance info
lamin info

# List all instances
lamin ls

# View instance details
lamin instance details
```

### Instance Migration

```bash
# Backup instance
lamin backup create

# Restore from backup
lamin backup restore backup_id

# Export instance metadata
lamin export instance-metadata.json
```

### Deleting Instances

```bash
# Delete instance (preserves data, removes metadata)
lamin delete --force instance-name

# This only removes the LaminDB metadata
# Actual data in storage location remains
```

## Performance Optimization

### Database Performance

```python
# Use connection pooling for PostgreSQL
# Configure in database server settings

# Optimize queries with indexes
# LaminDB creates indexes automatically for common queries
```

### Storage Performance

```bash
# Use appropriate storage classes
# S3: STANDARD for frequent access, INTELLIGENT_TIERING for mixed access

# Configure multipart upload thresholds
export AWS_CLI_FILE_IO_BANDWIDTH=100MB
```

### Cache Optimization

```python
# Pre-cache frequently used artifacts
artifacts = ln.Artifact.filter(key__startswith="reference/")
for artifact in artifacts:
    artifact.cache()  # Download to cache

# Use backed mode for large arrays
adata = artifact.backed()  # Don't load into memory
```

## Monitoring and Maintenance

### Health Checks

```python
import lamindb as ln

# Check database connection
try:
    ln.Artifact.filter().count()
    print("✓ Database connected")
except Exception as e:
    print(f"✗ Database error: {e}")

# Check storage access
try:
    test_artifact = ln.Artifact("test.txt", key="healthcheck.txt").save()
    test_artifact.delete(permanent=True)
    print("✓ Storage accessible")
except Exception as e:
    print(f"✗ Storage error: {e}")
```

### Logging

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# LaminDB operations will produce detailed logs
```

### Backup Strategy

```bash
# Regular database backups (PostgreSQL)
pg_dump -h hostname -U username -d database > backup_$(date +%Y%m%d).sql

# Storage backups (S3 versioning)
aws s3api put-bucket-versioning \
  --bucket my-bucket \
  --versioning-configuration Status=Enabled

# Metadata export
lamin export metadata_backup.json
```

## Troubleshooting

### Common Issues

**Issue: Cannot connect to instance**
```bash
# Check instance exists
lamin ls

# Re-connect
lamin connect instance-name
```

**Issue: Cache full**
```python
# Clear cache
import lamindb as ln
import shutil
shutil.rmtree(ln.settings.cache_dir)

# Set larger cache location
lamin cache set /larger/disk/cache
```

## Upgrade and Migration

### Upgrading LaminDB

```bash
# Upgrade after reviewing changelog and compatibility matrix
uv pip install --upgrade 'lamindb==2.5.1'

# Upgrade database schema
lamin migrate deploy
```

### Schema Compatibility

Check the compatibility matrix to ensure your database schema version is compatible with your installed LaminDB version.

### Breaking Changes

Major version upgrades may require migration:

```bash
# Check for breaking changes
lamin migrate check

# Review migration plan
lamin migrate plan

# Execute migration
lamin migrate deploy
```

## Best Practices

1. **Start local, scale cloud**: Develop locally, deploy to cloud for production
2. **Use PostgreSQL for production**: SQLite is only for development
3. **Configure appropriate cache**: Size cache based on working set
4. **Enable versioning**: Use S3/GCS versioning for data protection
5. **Monitor costs**: Track storage and compute costs in cloud deployments
6. **Document configuration**: Keep infrastructure-as-code for reproducibility
7. **Test backups**: Regularly verify backup and restore procedures
8. **Set up monitoring**: Implement health checks and alerting
9. **Use modules strategically**: Only install needed plugins to reduce complexity
10. **Plan for scale**: Consider concurrent users and data growth
