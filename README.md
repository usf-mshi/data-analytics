# data-analytics
Welcome to the Tidepool Data Analytics Respository. This is the home
for the code we use to download, clean, and analyze data for the Tidepool
Big Data Donation project.

## About our use of Python & R
We use the [Anaconda](https://www.anaconda.com/) distribution of Python & R.
You are welcome to install the full Anaconda installer, but will only need
Miniconda to get started.

## Getting started
1. Install [Miniconda](https://conda.io/miniconda.html) for your platform.
1. In a terminal, navigate to the data-analytics directory where the environment.yml 
is located.
1. Run `conda env create`. This will download all of the package dependencies
and install them in a virtual environment named tidepool-analytics. PLEASE NOTE: this
may take close to 30 minutes to complete.

## To list the Virtual Environments
Run `conda env list`

## To use the Virtual Environment
In Bash run `source activate tidepool-analytics`, or in the Anaconda Prompt 
run `conda activate tidepool-analytics` to start the environment.

Run `deactivate` to stop the environment.
