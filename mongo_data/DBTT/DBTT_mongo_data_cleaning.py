#!/usr/bin/env python
##############
# Data cleaning
#   - update some experimental temperatures
#   - standardize names where other names have been used
#   - keep only one of each true duplicate pair
#   - keep results from duplicate-condition experiments where conditions
#     are similar to the rest of the dataset
# Changes correspond for example to DBTT_Data7.csv to DBTT_Data8.csv differences
# TTM 2017-01-24
##############

import pymongo
import os
import sys
import mongo_data.DBTT.alloy_property_utilities as apu
from bson.objectid import ObjectId

def standardize_alloy_names(db, newcname, verbose=0):
    records = db[newcname].find()
    for record in records:
        alloy = record["Alloy"]
        std_name = apu.get_standardized_alloy_name(db, alloy, verbose)
        if std_name == alloy:
            pass
        elif std_name == None:
            raise ValueError("Alloy name %s in database %s, collection %s neither standard nor an alias." % (alloy,
                    db.name, newcname))
        else:
            db[newcname].update(
                {'_id':record["_id"]},
                {"$set":{"Alloy": std_name,
                         "old_Alloy_alias":alloy}}
                )
            if verbose > 0:
                print("Updated record %s old name %s with new alloy name %s" % (record["_id"], alloy, std_name)) 
    return

def standardize_flux_and_fluence(db, newcname, verbose=0):
    records = db[newcname].find({"flux_n_m2_sec":{"$ne":None}})
    for record in records:
        fluxval = record["flux_n_m2_sec"]
        fluenceval = record["fluence_n_m2"]
        newflux = fluxval / 10000.0
        newfluence = fluenceval / 10000.0
        db[newcname].update(
            {'_id':record["_id"]},
            {"$set":{"flux_n_cm2_sec":newflux, "fluence_n_cm2":newfluence}}
            )
        if verbose > 0:
            print("Updated record %s with flux %3.3f n/cm^2/sec and fluence %3.3f n/cm^2." % (record["_id"],newflux, newfluence))
    return

def update_experimental_temperatures(db, cname, verbose=1):
    """Update temperatures for a handful of experimental points
        whose reported temperature in the original data sheet 
        for ucsb ivar plus were incorrect.
            Alloys 6, 34, 35, 36, 37, 38 at fluence of 1.10e21 n/cm2, 
            flux of 2.30e14 n/cm2/sec should all be at 
            Temperature = 320 degrees C instead of 290 degrees C.
            Their CD temperature, however, remains at 290. 
    """ 
    id_list=list()
    orig_temp_list=list()
    flux=2.30e14 #n/cm2/sec
    fluence=1.10e21 #n/cm2
    newtemp=320 #degrees C
    num_list=[6,34,35,36,37,38]
    for num in num_list:
        aname = apu.look_up_name_or_number(db, num, "number")
        results = db[cname].find({"Alloy":aname,
                        "flux_n_cm2_sec":flux,
                        "fluence_n_cm2":fluence})
        for result in results:
            id_list.append(result["_id"])
            orig_temp_list.append(result["temperature_C"])
    #need to do actual temperature modification
    for modidx in range(0, len(id_list)):
        db[cname].update_one(
            {"_id":ObjectId(id_list[modidx])},
            {
                "$set":{
                    "original_reported_temperature_C": orig_temp_list[modidx],
                    "temperature_C": newtemp
                }
            }
        )
        if verbose > 0:
            print("%s: temperature updated" % id_list[modidx])
    return id_list

def flag_bad_cd1_points(db, cname, verbose=1):
    """Flag questionable CD delta sigma y values; when plotted against
        fluence, these values are clearly outliers from the 
        main curves that the rest of the points make.
        # Eventually substitute this method with an automatic
            way to reject outliers based on similarity to adjacent
            values, when filtered (e.g. by alloy and temp) and
            then plotted versus some x (like fluence or effective fluence)
    """
    odict=dict()
    odict[1]={'alloy_number':30,'flux_n_cm2_sec':8.0e10,'fluence_n_cm2':4.0e18,'temperature_C':290}
    odict[2]={'alloy_number':37,'flux_n_cm2_sec':1.0e12,'fluence_n_cm2':7.8e18,'temperature_C':290}
    odict[3]={'alloy_number':37,'flux_n_cm2_sec':2.6e11,'fluence_n_cm2':8.5e18,'temperature_C':290}
    odict[4]={'alloy_number':47,'flux_n_cm2_sec':8.4e11,'fluence_n_cm2':1.9e18,'temperature_C':290}
    odict[5]={'alloy_number':51,'flux_n_cm2_sec':8.0e10,'fluence_n_cm2':2.4e18,'temperature_C':290}
    odict[6]={'alloy_number':51,'flux_n_cm2_sec':3.2e11,'fluence_n_cm2':1.0e18,'temperature_C':290}
    odict[7]={'alloy_number':53,'flux_n_cm2_sec':8.0e10,'fluence_n_cm2':2.4e18,'temperature_C':290}
    id_list = list()
    reason_list=list()
    for okey in odict.keys():
        sdict = dict(odict[okey])
        anum = sdict.pop("alloy_number",None)
        aname = apu.look_up_name_or_number(db, anum, "number")
        sdict['Alloy'] = aname
        results = db[cname].find(sdict,{"_id":1})
        for result in results:
            id_list.append(result['_id'])
            reason_list.append("Outlier from response vs. fluence curve")
    if verbose > 0:
        for iidx in range(0, len(id_list)):
            print("%s: %s" % (id_list[iidx], reason_list[iidx]))
    return [id_list, reason_list]

def get_alloy_removal_ids(db, cname, alloylist=list(), verbose=1):
    """Removal of certain alloys from database
    """
    id_list = list()
    reason_list=list()
    for alloynum in alloylist:
        aname = apu.look_up_name_or_number(db, alloynum, "number")
        results = db[cname].find({'Alloy':aname},{"_id":1,"Alloy":1})
        for result in results:
            id_list.append(result['_id'])
            reason_list.append("Not considering alloy %s" % aname)
    if verbose > 0:
        for iidx in range(0, len(id_list)):
            print("%s: %s" % (id_list[iidx], reason_list[iidx]))
    return [id_list, reason_list]

def get_duplicate_conditions(db, cname, verbose=0):
    ddict=dict()
    id_list = list()
    pipeline=[
        {"$group": {"_id": {"Alloy":"$Alloy","flux_n_cm2_sec":"$flux_n_cm2_sec","fluence_n_cm2":"$fluence_n_cm2","temperature_C":"$temperature_C"},
                "count":{"$sum":1}}},
        { "$match": {"count": {"$gt" : 1}}}
        ]
    results = db[cname].aggregate(pipeline)
    condlist=list()
    for result in results:
        if verbose > 0:
            print(result)
        condlist.append(result['_id'])
    return condlist

def get_duplicate_ids_to_remove(db, cname, dupcheck="delta_sigma_y_MPa", verbose=1):
    """Get duplicate IDs to remove.
        True duplicates, remove the second copy.
        Where delta_sigma_y differs, remove the duplicate where
            conditions are least like the rest of the set.
            For eight such pairs, this happens to mean removing the
            smaller delta_sigma_y.
    """
    condlist = get_duplicate_conditions(db, cname)
    id_list=list()
    reason_list=list()
    for condition in condlist:
        if (verbose > 1):
            print(condition)
        rlist = list(db[cname].find(condition)) #should be two of each
        if not (len(rlist) == 2):
            raise ValueError("not exactly two duplicates for condition %s" % condition)
        if verbose > 1:
            print("Duplicate records for condition:")
            print(rlist[0])
            print(rlist[1])
        rval0 = rlist[0][dupcheck]
        rval1 = rlist[1][dupcheck]
        if rval0 == rval1:
            if verbose > 1:
                print("True duplicates.")
            id_list.append(rlist[1]['_id'])
            reason_list.append("Duplicate alloy, conditions, and delta_sigma_y.")
        else:
            if verbose > 1:
                print ("Not true duplicates.")
            if rval0 < rval1:
                id_list.append(rlist[0]['_id'])
            else:
                id_list.append(rlist[1]['_id'])
            reason_list.append("Duplicate alloy and conditions; remove lower delta_sigma_y.")
    if verbose > 0:
        for iidx in range(0, len(id_list)):
            print("%s: %s" % (id_list[iidx], reason_list[iidx]))
    return [id_list, reason_list]

def get_short_time_removal_ids(db, cname, minimum_sec = 30e6, verbose=1):
    """Removal of short time runs (e.g. for CD LWR)
    """
    id_list = list()
    reason_list=list()
    records = db[cname].find()
    for record in records:
        if record['time_sec'] < minimum_sec:
            id_list.append(record['_id'])
            reason_list.append("Not considering times under %3.3e seconds" % minimum_sec)
    if verbose > 0:
        for iidx in range(0, len(id_list)):
            print("%s: %s" % (id_list[iidx], reason_list[iidx]))
    return [id_list, reason_list]



def get_empty_flux_or_fluence_removal_ids(db, cname, verbose=1):
    """Removal of empty flux or fluence
    """
    id_list = list()
    reason_list=list()
    records = db[cname].find()
    for record in records:
        if record['flux_n_m2_sec'] == "" or record['fluence_n_m2'] == "":
            id_list.append(record['_id'])
            reason_list.append("Not considering empty flux or fluence.")
    if verbose > 0:
        for iidx in range(0, len(id_list)):
            print("%s: %s" % (id_list[iidx], reason_list[iidx]))
    return [id_list, reason_list]






if __name__=="__main__":
    print("Use from DataImportAndExport.py. Exiting.")
    sys.exit()
    from pymongo import MongoClient
    dbname="dbtt"
    client = MongoClient('localhost', 27017)
    db = client[dbname]
