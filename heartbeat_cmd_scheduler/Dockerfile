# Python runtime
FROM python:3.10

# Working Directory
WORKDIR /code

# copy required libraries
COPY ./requirements.txt /code/requirements.txt

# install required libraries
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# copy all files
COPY . /code

# run code
CMD python -u hb_cmd_scheduler.py