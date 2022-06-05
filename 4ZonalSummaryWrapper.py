"""
MIT License

Copyright (c) 2021 Ian Housman

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
#Script to take LandTrendr stack outputs and summarize across iGDEs for training and applying a model
####################################################################################################
from iGDE_lib import *
####################################################################################################
#User params defined in iGDE_lib.py
export_apply_tables = True
export_training_tables = False #Must be done after exporting apply tables
####################################################################################################
#Function to get an image collection of LandTrendr outputs for all bands to then summarize with iGDE zonal stats (means)
def getLT(ltCollection,ltBands):

  #Bring in LandTrendr collectino
  c = ee.ImageCollection(ltCollection)

  #Get the IDs of LandTrendr bands/indices runs
  ids = c.aggregate_array('system:index').getInfo()
  outC = None

  #Iterate across each ID and convert LandTrendr stack to a collection
  for id in ids:
    startYear = int(id.split('_')[-2])
    endYear = int(id.split('_')[-1])
    indexName = id.split('_{}_'.format(startYear))[0].split('Stack_')[1]
    
    ltStack = c.filter(ee.Filter.eq('system:index',id)).first()
    fit = simpleLTFit(ltStack,startYear,endYear,indexName).select(ltBands)

    if outC  == None:
      outC = fit
    else:
      outC = ee.ImageCollection(joinCollections(outC,fit))

  Map.addLayer(outC,{},'all fits',True)
  return outC
####################################################################################################
#Function to export model apply tables (tables to predict model across) for each year
def exportApplyTables(years,durFitMagSlope):
  #Iterate across each year to export a table of all iGDEs with zonal mean of LandTrendr outputs
  for yr in years:
    print(yr)
    
    #Get LandTrendr output for that year
    durFitMagSlopeYr = ee.Image(durFitMagSlope.filter(ee.Filter.calendarRange(yr,yr,'year')).first())
   
    #Compute zonal means
    igdesYr = durFitMagSlopeYr.reduceRegions(applyGDEs, ee.Reducer.mean(),scale,crs,transform,4)

    #Set zone field
    igdesYr = igdesYr.map(lambda f:f.set('year',yr))

    #Export table
    yrEnding = '_{}'.format(yr)
    outputName = outputApplyTableName + yrEnding
    t = ee.batch.Export.table.toAsset(igdesYr, outputName,outputApplyTableDir + '/'+outputName)
    print('Exporting:',outputName)
    t.start()
####################################################################################################
#Wrapper function to export apply tables for a set of years with a set of credentials
def batchExportApplyTables(startApplyYear,endApplyYear,durFitMagSlope):
  sets = new_set_maker(range(startApplyYear,endApplyYear+1),len(tokens))
  for i,years in enumerate(sets):
    initializeFromToken(tokens[i])
    print(ee.String('Token works!').getInfo())
    print(years)
    exportApplyTables(years,durFitMagSlope)
    trackTasks()

####################################################################################################
# Trying to add this in addStrata() makes it fail, so I am doing it after even though that is not great form.
# Ideally this would happen in exportApplyTables() -> addStrata()
def addMXStatus(outputApplyTableDir, originalApplyTableName, newApplyTableName, years):
  for yr in years:
    print('Modeling:',yr)

    #Bring in apply table
    applyTrainingTableYr = ee.FeatureCollection('{}/{}_{}'.format(outputApplyTableDir,originalApplyTableName,yr))

    # Add MXStatus
    mxStatus = ee.FeatureCollection('projects/igde-work/igde-data/iGDE_MXstatus').select(['POLYGON_ID','MXStatus'])
    applyTrainingTableYr = joinFeatureCollectionsReverse(mxStatus, applyTrainingTableYr, 'POLYGON_ID')

    #Export table
    yrEnding = '_{}'.format(yr)
    outputName = newApplyTableName + yrEnding
    t = ee.batch.Export.table.toAsset(applyTrainingTableYr, outputName, outputApplyTableDir + '/' + outputName)
    print('Exporting:',outputName)
    t.start()
  return applyTrainingTableYr

####################################################################################################
#Wrapper function to export apply tables for a set of years with a set of credentials
def batchExportMXStatus(startApplyYear,endApplyYear,outputApplyTableDir, originalApplyTableName, newApplyTableName):
  sets = new_set_maker(range(startApplyYear,endApplyYear+1),len(tokens))
  for i,years in enumerate(sets):
    initializeFromToken(tokens[i])
    print(ee.String('Token works!').getInfo())
    print(years)
    addMXStatus(outputApplyTableDir, originalApplyTableName, newApplyTableName, years)
    trackTasks()

####################################################################################################  
def getTrainingTable(startTrainingYear,endTrainingYear,dgwNullValue = -999,maxDGW = 20,minDGW = 0):
  years = range(startTrainingYear,endTrainingYear+1)
  outTraining = []
  for yr in years:
    print(yr)
    #Set up fields to select from training features
    #Will only need the DGW for that year and id
    #Will pull geometry and all other fields from that year's apply table
    yearDGWField = 'Depth{}'.format(yr)
    fromFields = [yearDGWField,'POLYGON_ID','STN_ID']
    toFields = ['dgw','POLYGON_ID','STN_ID']
  
    igdesYr = trainingGDEs.select(fromFields,toFields)
    
    igdesYr = igdesYr.map(lambda f: f.set('dgw',ee.Number(f.get('dgw')).float()))
    #Filter out training igdes for that year
    igdesYr = igdesYr.filter(ee.Filter.neq('dgw',dgwNullValue))
    
    igdesYr = igdesYr.filter(ee.Filter.lte('dgw',maxDGW))
    igdesYr = igdesYr.filter(ee.Filter.gte('dgw',minDGW))
    
    
    #Bring in apply training table to join to to get goemetry and all other fields
    yrEnding = '_{}'.format(yr)
    outputName = outputApplyTableName+ yrEnding
    applyTrainingTableYr = outputApplyTableDir + '/'+outputName
    applyTrainingTableYr = ee.FeatureCollection(applyTrainingTableYr)
    igdesYr = joinFeatureCollectionsReverse(igdesYr,applyTrainingTableYr,'POLYGON_ID')

    outTraining.append(igdesYr)
    
  #Combine all years into a single collection and export
  outTraining = ee.FeatureCollection(outTraining).flatten()
  Map.addLayer(outTraining,{'strokeColor':'F0F','layerType':'geeVectorImage'},'Training Features',False)
  t = ee.batch.Export.table.toAsset(outTraining, outputTrainingTableName,outputTrainingTablePath)
  print('Exporting:',outputTrainingTableName)
  t.start()

####################################################################################################
#Function calls
if export_apply_tables:
  #Get fitted LT collection
  durFitMagSlope = getLT(ltCollection,ltBands)

  #First, export model apply tables
  batchExportApplyTables(startApplyYear,endApplyYear,durFitMagSlope)

  #Add MXStatus to apply tables
  if 'MXStatus' in predictors:
    batchExportMXStatus(startApplyYear,endApplyYear,outputApplyTableDir, 'dgwRFModelingApplyTable4', 'dgwRFModelingApplyTable5')

elif export_training_tables:
  #Once apply tables are finished exporting, export model training table
  getTrainingTable(startTrainingYear,endTrainingYear,dgwNullValue,maxDGW,minDGW)

#View map
# Map.view()
