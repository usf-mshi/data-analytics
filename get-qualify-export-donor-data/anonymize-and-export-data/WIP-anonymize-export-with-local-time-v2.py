#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
description: Anonymize and export Tidepool data
version: 0.0.1
created: 2018-02-21
author: Ed Nykaza
dependencies:
    * requires get-donor-data virtual environment (see readme for instructions)
    * requires Tidepool json data (e.g., PHI-jill-jellyfish.json)
    * requires commandline tool 'jq' for making the pretty json file
license: BSD-2-Clause
TODO:
* [] move code that is used by multiple scripts to a utility folder/library
* [] pull in jill-jellyfish.json dataset from AWS if no file is given
"""

# %% REQUIRED LIBRARIES
import pandas as pd
import datetime as dt
import numpy as np
import os
import sys
import shutil
import glob
import argparse
import hashlib
import json
import ast
sys.path.insert(0, "../")
import environmentalVariables

# %% USER INPUTS
#codeDescription = "Anonymize and export Tidepool data"
#
#parser = argparse.ArgumentParser(description=codeDescription)
#
#parser.add_argument("-i",
#                    "--input-file-path",
#                    dest="inputPath",
#                    default=os.path.join(".", "example-data", ""),
#                    help="path of .json data to be anonymized and exported")
#
#parser.add_argument("-u",
#                    "--user-name",
#                    dest="userName",
#                    default="PHI-jill-jellyfish.json",
#                    help="name of .json file to be anonymized and exported")
#
#parser.add_argument("--data-field-list",
#                    dest="dataFieldExportList",
#                    default=os.path.join(".",
#                                         "example-data",
#                                         "dataFieldExportList.csv"),
#                    help="a csv file that contains a list of fields to export")
#
#parser.add_argument("--salt",
#                    dest="salt",
#                    default="no salt specified",
#                    help="salt used in the hashing algorithm")
#
#parser.add_argument("-o",
#                    "--output-data-path",
#                    dest="exportPath",
#                    default=os.path.join(".", "example-data", "export", ""),
#                    help="the path where the data is exported")
#
#parser.add_argument("--output-name",
#                    dest="outputName",
#                    default="jill-jellyfish",
#                    help="name of exported files")
#
#parser.add_argument("--output-format",
#                    dest="exportFormat",
#                    default="xlsx",
#                    help="the format of the exported data. Export options " +
#                         "include 'json', 'xlsx', 'csv', and 'all'")
#
#parser.add_argument("--start-date",
#                    dest="startDate",
#                    default="1900-01-01",
#                    help="filter data by startDate and EndDate")
#
#parser.add_argument("--end-date",
#                    dest="endDate",
#                    default=dt.datetime.now().strftime("%Y-%m-%d"),
#                    help="filter data by startDate and EndDate")
#
#parser.add_argument("--remove-dates",
#                    dest="removeDates",
#                    default="",
#                    help="an array of dates to remove, in the following " +
#                         "format: '%Y-%m-%d, %Y-%m-%d, ...'")
#
#args = parser.parse_args()


# %% FUNCTIONS
def removeByDates(df, daysToRemove):
    removeDates = pd.to_datetime(daysToRemove).date
    df = df[~(pd.to_datetime(df.time).dt.date.isin(removeDates))]

    return df


def filterByDates(df, startDate, endDate):

    # filter by qualified start & end date, and sort
    df = \
        df[(df.time >= startDate) &
           (df.time <= (endDate + "T23:59:59"))]

    return df

def filterByDatesExceptUploadsAndSettings(df, startDate, endDate):

    # filter by qualified start & end date, and sort
    uploadEventsSettings = df[((df.type == "upload") |
                               (df.type == "deviceEvent") |
                               (df.type == "pumpSettings"))]

    theRest = df[~((df.type == "upload") |
                  (df.type == "deviceEvent") |
                  (df.type == "pumpSettings"))]

    theRest = theRest[(theRest["est.localTime"] >= startDate) &
                      (theRest["est.localTime"] <= (endDate + "T23:59:59"))]

    df = pd.concat([uploadEventsSettings, theRest])

    return df



def filterByRequiredDataFields(df, requiredDataFields):

    dfExport = pd.DataFrame()
    for fIndex in range(0, len(requiredDataFields)):
        if requiredDataFields[fIndex] in df.columns.values:
            dfExport = pd.concat([dfExport, df[requiredDataFields[fIndex]]],
                                 axis=1)

    return dfExport


def tempRemoveFields(df):
    removeFields = ["basalSchedules",
                    "bgTarget",
                    "bgTargets",
                    "carbRatio",
                    "carbRatios",
                    "insulinSensitivity",
                    "insulinSensitivities"]

    tempRemoveFields = list(set(df) & set(removeFields))
    tempDf = df[tempRemoveFields]
    df = df.drop(columns=tempRemoveFields)

    return df, tempDf


def flattenJson(df, requiredDataFields):

    # remove fields that we don't want to flatten
    df, holdData = tempRemoveFields(df)

    # remove [] from annotations field
    df = removeBrackets(df, "annotations")

    # get a list of data types of column headings
    columnHeadings = list(df)  # ["payload", "suppressed"]

    # loop through each columnHeading
    for colHead in columnHeadings:
        # if the df field has embedded json
        if "{" in df[df[colHead].notnull()][colHead].astype(str).str[0].values:
            # grab the data that is in brackets
            jsonBlob = df[colHead][df[colHead].astype(str).str[0] == "{"]

            # replace those values with nan
            df.loc[jsonBlob.index, colHead] = np.nan

            # turn jsonBlog to dataframe
            newDataFrame = pd.DataFrame(jsonBlob.tolist(),
                                        index=jsonBlob.index)
            newDataFrame = newDataFrame.add_prefix(colHead + '.')
            newColHeadings = list(newDataFrame)

            # put df back into the main dataframe
            for newColHeading in list(set(newColHeadings) &
                                      set(requiredDataFields)):
                tempDataFrame = newDataFrame[newColHeading]
                df = pd.concat([df, tempDataFrame], axis=1)

    # add the fields that were removed back in
    df = pd.concat([df, holdData], axis=1)

    return df


def removeBrackets(df, fieldName):
    if fieldName in list(df):
        df.loc[df[fieldName].notnull(), fieldName] = \
            df.loc[df[fieldName].notnull(), fieldName].str[0]

    return df


def removeNegativeDurations(df):
    if "duration" in list(df):
        nNegativeDurations = sum(df.duration < 0)
        if nNegativeDurations > 0:
            df = df[~(df.duration < 0)]

    return df, nNegativeDurations


def removeInvalidCgmValues(df):

    nBefore = len(df)
    # remove values < 38 and > 402 mg/dL
    df = df.drop(df[((df.type == "cbg") &
                     (df.value < 2.109284236597303))].index)
    df = df.drop(df[((df.type == "cbg") &
                     (df.value > 22.314006924003046))].index)
    nRemoved = nBefore - len(df)

    return df, nRemoved


def tslimCalibrationFix(df):
    searchfor = ['tan']
    tandemDataIndex = ((df.deviceId.str.contains('|'.join(searchfor))) &
                       (df.type == "deviceEvent"))
#    nTandemData = sum(tandemDataIndex)

    if "payload.calibration_reading" in list(df):
        payloadCalReadingIndex = df["payload.calibration_reading"].notnull()
#        nPayloadCalReadings = sum(payloadCalReadingIndex)

        nTandemAndPayloadCalReadings = sum(tandemDataIndex &
                                           payloadCalReadingIndex)

        if nTandemAndPayloadCalReadings > 0:
            # if reading is > 30 then it is in the wrong units
            if df["payload.calibration_reading"].min() > 30:
                df.loc[payloadCalReadingIndex, "value"] = \
                    df[tandemDataIndex & payloadCalReadingIndex] \
                    ["payload.calibration_reading"] / 18.01559
            else:
                df.loc[payloadCalReadingIndex, "value"] = \
                    df[tandemDataIndex &
                        payloadCalReadingIndex]["payload.calibration_reading"]
    else:
        nTandemAndPayloadCalReadings = 0
    return df, nTandemAndPayloadCalReadings


def hashScheduleNames(df, salt, userID):

    scheduleNames = ["basalSchedules",
                     "bgTargets",
                     "carbRatios",
                     "insulinSensitivities"]

    # loop through each of the scheduleNames that exist
    for scheduleName in scheduleNames:
        # if scheduleName exists, find the rows that have the scheduleName
        if scheduleName in list(df):
            scheduleNameDataFrame = df[df[scheduleName].notnull()]
            scheduleNameRows = scheduleNameDataFrame[scheduleName].index
            # loop through each schedule name row
            uniqueScheduleNames = []
            for scheduleNameRow in scheduleNameRows:
                scheduleNameKeys = \
                    list(ast.literal_eval(scheduleNameDataFrame[scheduleName]
                        [scheduleNameRow]).keys())
                uniqueScheduleNames = list(set(uniqueScheduleNames +
                                               scheduleNameKeys))
            # loop through each unique schedule name and create a hash
            for uniqueScheduleName in uniqueScheduleNames:
                hashedScheduleName = \
                    hashlib.sha256((uniqueScheduleName + salt + userID).
                                   encode()).hexdigest()[0:8]
                # find and replace those names in the json blob
                newScheduleName = \
                    pd.DataFrame(scheduleNameDataFrame[scheduleName]
                                 .astype(str).str.replace(
                                         uniqueScheduleName,
                                         hashedScheduleName))

                scheduleNameDataFrame = \
                    scheduleNameDataFrame.drop(columns=scheduleName)
                scheduleNameDataFrame[scheduleName] = newScheduleName

            # drop and reattach the new data
            df = df.drop(columns=scheduleName)
            df = pd.merge(df, scheduleNameDataFrame.loc[:, ["time",
                                                            scheduleName]],
                          how="left", on="time")
    return df


def hashData(df, columnHeading, lengthOfHash, salt, userID):

    df[columnHeading] = \
        (df[columnHeading].astype(str) + salt + userID).apply(
        lambda s: hashlib.sha256(s.encode()).hexdigest()[0:lengthOfHash])

    return df


def hashWithSalt(df, hashSaltFields, salt, userID):

    for hashSaltField in hashSaltFields:
        if hashSaltField in df.columns.values:
            df.loc[df[hashSaltField].notnull(), hashSaltField] = \
                hashData(pd.DataFrame(df.loc[df[hashSaltField].notnull(),
                                             hashSaltField]),
                         hashSaltField, 8, salt, userID)

    # also hash the schedule names
    df = hashScheduleNames(df, salt, userID)

    return df


def exportPrettyJson(df, exportFolder, fileName, csvExportFolder):
    # first load in all csv files
    csvFiles = glob.glob(csvExportFolder + "*.csv")
    bigTable = pd.DataFrame()
    for csvFile in csvFiles:
        bigTable = pd.concat([bigTable,
                              pd.read_csv(csvFile,
                                          low_memory=False,
                                          index_col="jsonRowIndex")])
    # then sort
    bigTable = bigTable.sort_values("time")

    # make a hidden file
#    hiddenJsonFile = exportFolder + "." + fileName + ".json"
    jsonExportFileName = exportFolder + fileName + ".json"
    bigTable.to_json(jsonExportFileName, orient='records')
#    bigTable.to_json(hiddenJsonFile, orient='records')
    # make a pretty json file for export

#    os.system("jq '.' " + hiddenJsonFile + " > " + jsonExportFileName)
    # delete the hidden file
#    os.remove(hiddenJsonFile)

    return


def filterAndSort(groupedDF, filterByField, sortByField):
    filterDF = groupedDF.get_group(filterByField).dropna(axis=1, how="all")
    filterDF = filterDF.sort_values(sortByField)
    return filterDF


def removeManufacturersFromAnnotationsCode(df):

    # remove manufacturer from annotations.code
    manufacturers = ["animas/",
                     "bayer/",
                     "carelink/",
                     "insulet/",
                     "medtronic/",
                     "tandem/"]

    annotationFields = [
        "annotations.code",
        "suppressed.annotations.code",
        "suppressed.suppressed.annotations.code"
        ]

    for annotationField in annotationFields:
        if annotationField in df.columns.values:
            if sum(df[annotationField].notnull()) > 0:
                df[annotationField] = \
                    df[annotationField].str. \
                    replace("|".join(manufacturers), "")

    return df


def mergeWizardWithBolus(df, csvExportFolder):

    if (("bolus" in set(df.type)) and ("wizard" in set(df.type))):
        bolusData = pd.read_csv(csvExportFolder + "bolus.csv",
                                low_memory=False)
        wizardData = pd.read_csv(csvExportFolder + "wizard.csv",
                                 low_memory=False)

        # merge the wizard data with the bolus data
        wizardData["calculatorId"] = wizardData["id"]
        wizardDataFields = [
            "bgInput",
            "bgTarget.high",
            "bgTarget.low",
            "bgTarget.range",
            "bgTarget.target",
            "bolus",
            "carbInput",
            "calculatorId",
            "insulinCarbRatio",
            "insulinOnBoard",
            "insulinSensitivity",
            "recommended.carb",
            "recommended.correction",
            "recommended.net",
            "units",
        ]
        keepTheseWizardFields = \
            set(wizardDataFields).intersection(list(wizardData))
        bolusData = pd.merge(bolusData,
                             wizardData[list(keepTheseWizardFields)],
                             how="left",
                             left_on="id",
                             right_on="bolus")

        mergedBolusData = bolusData.drop("bolus", axis=1)
    else:
        mergedBolusData = pd.DataFrame()

    return mergedBolusData


def exportCsvFiles(df, exportFolder, fileName):
    csvExportFolder = os.path.join(exportFolder, "." + fileName + "-csvs", "")
    if not os.path.exists(csvExportFolder):
        os.makedirs(csvExportFolder)

    groupedData = df.groupby(by="type")
    for dataType in set(df[df.type.notnull()].type):
        csvData = filterAndSort(groupedData, dataType, "time")
        csvData.index.name = "jsonRowIndex"
        csvData.to_csv(csvExportFolder + dataType + ".csv")

    # merge wizard data with bolus data, and delete wizard data
    bolusWithWizardData = mergeWizardWithBolus(df, csvExportFolder)
    if len(bolusWithWizardData) > 0:
        bolusWithWizardData.to_csv(csvExportFolder + "bolus.csv", index=False)
    if os.path.exists(csvExportFolder + "wizard.csv"):
        os.remove(csvExportFolder + "wizard.csv")

    return csvExportFolder


def exportExcelFile(csvExportFolder, exportFolder, fileName):
    writer = pd.ExcelWriter(exportFolder + fileName + ".xlsx")
    csvFiles = sorted(os.listdir(csvExportFolder))
    for csvFile in csvFiles:
        dataName = csvFile[:-4]
        tempCsvData = pd.read_csv(os.path.join(csvExportFolder,
                                               dataName + ".csv"),
                                  low_memory=False,
                                  index_col="jsonRowIndex")
        tempCsvData.to_excel(writer, dataName)
    writer.save()

    return


# %% MODIFICATIONS

dateStamp = "2018-02-28"
qualificationCriteria = "/ed/projects/data-analytics/get-donor-data/data/dexcom-qualification-criteria.json"

with open(qualificationCriteria) as json_data:
    qualCriteria = json.load(json_data)


donorCsvFolder = "/ed/projects/data-analytics/get-donor-data/data/" + \
    "PHI-2018-02-28-donor-data/PHI-2018-02-28-donorCsvFolder-w-local-time-est/"


#donorQualifyFolder = "/ed/projects/data-analytics/get-donor-data/data/" + \
#    "PHI-2018-02-28-donor-data/2018-02-28-qualified/"


## load in list of unique donors
#uniqueDonorPath = "/ed/projects/data-analytics/get-donor-data/data/" + \
#    "PHI-2018-02-28-donor-data/PHI-2018-02-28-uniqueDonorList-dexcom-local-time.csv"
#uniqueDonors = pd.read_csv(uniqueDonorPath, index_col="dIndex", low_memory=False)

## %% GLOBAL VARIABLES
qualifiedOn = '2018-05-03'
phiDateStamp = "PHI-" + dateStamp

#criteriaMaxCgmPointsPerDay = \
#    1440 / qualCriteria["timeFreqMin"]

donorFolder = "/ed/projects/data-analytics/get-donor-data/data/" + \
    "PHI-2018-02-28-donor-data/"

aMFileName = os.path.join(donorFolder, phiDateStamp +
                          "-with-local-time-est-qualified-on-" + qualifiedOn +
                          "-for-" + qualCriteria["name"] + "-metadata.csv")

uniqueDonors = pd.read_csv(aMFileName, low_memory=False, index_col="dIndex")


# #%% GLOBAL VARIABLES
# input folder(s)
#userName = args.userName
#outputFileName = args.outputName
#jsonFilePath = os.path.join(args.inputPath, userName)
#if not os.path.isfile(jsonFilePath):
#    sys.exit("{0} is not a valid file path".format(jsonFilePath))
#
#userID = userName[
#        (userName.find("PHI-") + 4):
#        (userName.find(".json"))]

#dataFieldPath = args.dataFieldExportList
#if not os.path.isfile(dataFieldPath):
#    sys.exit("{0} is not a valid file path".format(dataFieldPath))
#
## create output folder(s)
exportFolder = "/ed/projects/data-analytics/get-donor-data/data/" + \
    "PHI-2018-02-28-donor-data/2018-02-28-qualified-for-Dexcom/w-local-time-estimates/"
#if not os.path.exists(exportFolder):
#    os.makedirs(exportFolder)

dataFieldPath = "/ed/projects/data-analytics/get-donor-data/data/" + \
    "dataFieldExportListLillyDexcom-wEstLocalTime.csv"

dataFieldExportList = pd.read_csv(dataFieldPath)
requiredDataFields = \
    list(dataFieldExportList.loc[dataFieldExportList.include.fillna(False),
                                 "dataFieldList"])

salt = os.environ["BIGDATA_SALT"]

hashSaltFields = list(dataFieldExportList.loc[
        dataFieldExportList.hashNeeded.fillna(False), "dataFieldList"])


exportFormat = "all"

qualifiedDonorIndex = uniqueDonors[((uniqueDonors["D.topTier"].notnull()) &
                            (uniqueDonors["D.topTier"] != "D0"))].index
for dIndex in qualifiedDonorIndex:
    userID = uniqueDonors.loc[dIndex, "userID"]
    hashID = uniqueDonors.loc[dIndex, "hashID"]
    qualTier = uniqueDonors.loc[dIndex, "D.topTier"]
    startDate = uniqueDonors.loc[dIndex, qualTier + ".qualified.beginDate"]
    endDate = uniqueDonors.loc[dIndex, qualTier + ".qualified.endDate"]
    csvFileName = os.path.join(donorCsvFolder, "PHI-" + userID + ".csv")
    outputFileName = qualTier + "_" + hashID
    if os.path.exists(csvFileName):
        phiUserID = "PHI-" + userID
        data = pd.read_csv(os.path.join(donorCsvFolder, phiUserID + ".csv"),
                           low_memory=False)


#    qualTier = data[tier][dIndex]
#    userID = data.userID[dIndex]
#    hashID = data.hashID[dIndex]
#    bDay = anonymizeBirthdayOrDiagnosisDate(data.bDay[dIndex])
#    dDay = anonymizeBirthdayOrDiagnosisDate(data.dDay[dIndex])
#    startDate = data[qualTier + ".qualified.beginDate"][dIndex]
#    endDate = data[qualTier + ".qualified.endDate"][dIndex]
#    nDaysToDeliver = \
#        data[qualTier + ".qualified.nDaysToDeliever"][dIndex].astype(int)
#
#    inputPath = donorJsonDataFolder
#    userName = "PHI-" + userID + ".json"
#    dataFieldExportList = args.dataFieldExportList
#    exportPath = exportFolder
#    exportName = qualTier + "_" + hashID
#    exportFormat = "all"
#    removeDates = ""





        # %% MODIFICATIONS (2)
        # filter by data in which we don't have a good local time estimate
        # local estimates imputed by gaps > 30 and those that are uncertain
        data = data[~((data["est.gapSize"] > 30) |
                (data["est.type"] == "UNCERTAIN"))]

# %% START OF CODE
## load json file
#data = pd.read_json(jsonFilePath, orient="records")

        # remove data between start and end dates
        data = filterByDatesExceptUploadsAndSettings(data, startDate, endDate)

## remove dates (optional input used by some data partners)
#data = removeByDates(data, args.removeDates.split(","))

## flatten embedded json, if it exists
#data = flattenJson(data, requiredDataFields)

        # only keep the data fields that are approved
        data = filterByRequiredDataFields(data, requiredDataFields)

# %% clean up data
        # remove negative durations
        data, numberOfNegativeDurations = removeNegativeDurations(data)

        # get rid of cgm values too low/high (< 38 & > 402 mg/dL)
        data, numberOfInvalidCgmValues = removeInvalidCgmValues(data)

        # Tslim calibration bug fix
        data, numberOfTandemAndPayloadCalReadings = tslimCalibrationFix(data)

        # hash the required data/fields
        data = hashWithSalt(data, hashSaltFields, salt, userID)

        # remove device manufacturer from annotations.code
        data = removeManufacturersFromAnnotationsCode(data)

# %% sort and export data
        # sort data by time
        data = data.sort_values("time")

        # all exports are based off of csv data
        csvExportFolder = exportCsvFiles(data, exportFolder, outputFileName)

        if exportFormat in ["json", "all"]:
            exportPrettyJson(data, exportFolder, outputFileName, csvExportFolder)

        if exportFormat in ["xlsx", "all"]:
            exportExcelFile(csvExportFolder, exportFolder, outputFileName)

        if exportFormat in ["csv", "all"]:
            # unhide the csv files
            unhiddenCsvExportFolder = \
                os.path.join(exportFolder, outputFileName + "-csvs", "")
            os.rename(csvExportFolder, unhiddenCsvExportFolder)
        else:
            shutil.rmtree(csvExportFolder)

        print("done with", userID, "gapData=", data["est.gapSize"].notnull().sum())