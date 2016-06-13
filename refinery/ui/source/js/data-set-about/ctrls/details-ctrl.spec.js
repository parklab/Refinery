'use strict';

describe('Controller: DetailsCtrl', function () {
  var ctrl;
  var scope;
  var factory;
  var $controller;

  beforeEach(module('refineryApp'));
  beforeEach(module('refineryDataSetAbout'));
  beforeEach(inject(function (
    $rootScope, _$controller_, _dataSetAboutFactory_, $window
  ) {
    scope = $rootScope.$new();
    $controller = _$controller_;
    ctrl = $controller('AboutDetailsCtrl', {
      $scope: scope
    });
    factory = _dataSetAboutFactory_;
    $window.externalAssayUuid = 'x508x83x-x9xx-4740-x9x7-x7x0x631280x';
  }));

  it('refineryDataSetAbout ctrl should exist', function () {
    expect(ctrl).toBeDefined();
  });

  it('Data & UI displays variables should exist for views', function () {
    expect(ctrl.dataSet).toEqual({});
    expect(ctrl.studies).toEqual([]);
    expect(ctrl.assays).toEqual({});
    expect(ctrl.fileStoreItem).toEqual({});
  });

  describe('RefreshDataSetStats', function () {
    it('refreshDataSetStats is method', function () {
      expect(angular.isFunction(ctrl.refreshDataSetStats)).toBe(true);
    });

    it('RefreshDataSetStats returns promise', function () {
      var mockDataSets = false;
      spyOn(factory, 'getDataSet').and.callFake(function () {
        return {
          then: function () {
            mockDataSets = true;
          }
        };
      });
      expect(mockDataSets).toEqual(false);
      ctrl.refreshDataSetStats();
      expect(mockDataSets).toEqual(true);
    });
  });
});
