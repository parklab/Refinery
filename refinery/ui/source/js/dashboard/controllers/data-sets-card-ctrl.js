/**
 * Data Sets Card Ctrl
 * @namespace DataSetsCardCtrl
 * @desc Controller for data sets card component on dashboard component.
 * Child component of dashboard component
 * @memberOf refineryApp.refineryDashboard
 */
(function () {
  'use strict';

  angular
    .module('refineryDashboard')
    .controller('DataSetsCardCtrl', DataSetsCardCtrl);

  DataSetsCardCtrl.$inject = [
    '$log',
    '$scope',
    '$uibModal',
    '$window',
    '_',
    'DataSetSearchApi',
    'dataSetCardFactory',
    'primaryGroupService',
    'settings'
  ];

  function DataSetsCardCtrl (
    $log,
    $scope,
    $uibModal,
    $window,
    _,
    DataSetSearchApi,
    dataSetCardFactory,
    primaryGroupService,
    settings
  ) {
    var vm = this;
    vm.currentPage = 1;
    vm.dataSets = [];
    vm.dataSetsError = false;
    vm.filterDataSets = filterDataSets;
    vm.groupFilter = { selectedName: 'All' };
    vm.isFiltersEmpty = isFiltersEmpty;
    vm.isLoggedIn = settings.djangoApp.userId !== undefined;
    vm.loadingDataSets = true;
    vm.numPages = 0;
    vm.openDataSetDeleteModal = openDataSetDeleteModal;
    vm.openDataSetTransferModal = openDataSetTransferModal;
    vm.openPermissionEditor = openPermissionEditor;
    vm.itemsPerPage = 20;
    vm.pageStartOffset = 0;
    vm.pageChangedUpdate = pageChangedUpdate;
    vm.params = { limit: vm.itemsPerPage, offset: vm.pageStartOffset };
    vm.primaryGroupID = primaryGroupService.primaryGroup.id;
    vm.refreshDataSets = refreshDataSets;
    vm.resetDataSetSearch = resetDataSetSearch;
    vm.searchDataSets = searchDataSets;
    vm.areDataSetsTextSearched = false; // data sets text searched via solr api
    vm.searchQueryDataSets = '';
    vm.totalDataSets = dataSetCardFactory.dataSetStats.totalCount;

    /**
     * @name filterDataSets
     * @desc  View method used to update the params with group and own perms
     * @memberOf refineryDashboard.DataSetsCardCtrl
     * @param {string} permsID - string with the perms name or ID
    **/
    function filterDataSets (permsID) {
      if (permsID === 'public') {
        if (vm.groupFilter.public) {
          vm.params.public = 'True';
        } else {
          delete vm.params.public; // public false is unused
        }
      } else if (permsID === 'owned') {
        if (vm.groupFilter.owned) {
          vm.params.is_owner = 'True';
        } else {
          delete vm.params.is_owner; // owned false is unused
        }
      } else if (!permsID) {
        delete vm.params.group;
      } else {
        vm.params.group = permsID;
      }
      refreshDataSets();
    }

    /**
     * @name pageChangedUpdate
     * @desc  View method for updating data sets based on page number
     * @memberOf refineryDashboard.DataSetsCardCtrl
    **/
    function pageChangedUpdate () {
      vm.pageStartOffset = vm.itemsPerPage * vm.currentPage - vm.itemsPerPage;
      vm.params.offset = vm.pageStartOffset;
      vm.refreshDataSets();
    }

    /**
     * @name refreshDataSets
     * @desc  View method for updating the data set list
     * @memberOf refineryDashboard.DataSetsCardCtrl
    **/
    function refreshDataSets () {
      vm.loadingDataSets = true;
      dataSetCardFactory.getDataSets(vm.params).then(function () {
        vm.searchQueryDataSets = '';
        vm.loadingDataSets = false;
        vm.dataSets = dataSetCardFactory.dataSets.slice(0, vm.itemsPerPage);
        vm.totalDataSets = dataSetCardFactory.dataSetStats.totalCount;
        vm.numPages = Math.ceil(vm.totalDataSets / vm.itemsPerPage);
        vm.dataSetsError = false;
        vm.areDataSetsTextSearched = false;
      }, function (error) {
        vm.loadingDataSets = false;
        $log.error(error);
        vm.dataSetsError = true;
      });
    }

    /**
     * @name openDataSetDeleteModal
     * @desc  Opens deletion modal
     * @memberOf refineryDashboard.DataSetsCardCtrl
     * @param {obj} dataSet - data set object
    **/
    function openDataSetDeleteModal (dataSet) {
      var datasetDeleteDialogUrl = $window.getStaticUrl(
        'partials/dashboard/partials/dataset-delete-dialog.html'
      );
      var modalInstance = $uibModal.open({
        backdrop: 'static',
        keyboard: false,
        templateUrl: datasetDeleteDialogUrl,
        controller: 'DataSetDeleteCtrl as modal',
        resolve: {
          config: function () {
            return {
              model: 'data_sets',
              uuid: dataSet.uuid
            };
          },
          dataSet: dataSet
        }
      });

      modalInstance.result.then(function () {
        // user confirmed deletion
        refreshDataSets();
        vm.dashboardParentCtrl.refreshEvents = true;
      });
    }

     /**
     * @name openDataSetTransferModal
     * @desc  Opens data set transfer modal
     * @memberOf refineryDashboard.DataSetsCardCtrl
     * @param {obj} dataSet - data set obj
    **/
    function openDataSetTransferModal (dataSet) {
      var modalInstance = $uibModal.open({
        component: 'rpDataSetTransferModal',
        resolve: {
          config: function () {
            return {
              uuid: dataSet.uuid,
              title: dataSet.title
            };
          }
        }
      });

      modalInstance.result.then(
        function () {},
        function () {
          // when modal is closed
          refreshDataSets();
          vm.dashboardParentCtrl.refreshEvents = true;
        });
    }

    /**
     * @name openPermissionEditor
     * @desc  Opens sharing modal (common component)
     * @memberOf refineryDashboard.DataSetsCardCtrl
     * @param {string} dataSetUuid - data set object uuid
    **/
    /** view method to open the permissions modal component, in commons
     *  directive*/
    function openPermissionEditor (dataSetUuid) {
      var modalInstance = $uibModal.open({
        component: 'rpPermissionEditorModal',
        resolve: {
          config: function () {
            return {
              model: 'data_sets',
              uuid: dataSetUuid
            };
          }
        }
      });

      modalInstance.result.then(function () {
        refreshDataSets();
      });
    }

    /**
     * @name resetDataSetSearch
     * @desc  View method to reset data search query
     * @memberOf refineryDashboard.DataSetsCardCtrl
    **/
    function resetDataSetSearch () {
      vm.searchQueryDataSets = '';
      vm.areDataSetsTextSearched = false;
      vm.refreshDataSets();
    }

    /**
     * @name searchDataSets
     * @desc  View method to search and update data sets
     * @memberOf refineryDashboard.DataSetsCardCtrl
     * @param {string} query - user entered query for data set search
    **/
    function searchDataSets (query) {
      // reset perm filter until we can search & check perms
      vm.groupFilter = { selectedName: 'All' };
      vm.params = { limit: vm.itemsPerPage, offset: vm.pageStartOffset };
      if (query && query.length > 1) {
        vm.loadingDataSets = true;
        var apiRequest = new DataSetSearchApi(query);
        apiRequest(200).then(function (response) {
          vm.dataSets = response.data;
          angular.copy(response.data, dataSetCardFactory.dataSets);
          dataSetCardFactory.dataSetStats.totalCount = response.data.length;
          vm.dataSets = dataSetCardFactory.dataSets.slice(0, vm.itemsPerPage);
          vm.totalDataSets = dataSetCardFactory.dataSetStats.totalCount;
          vm.numPages = Math.ceil(vm.totalDataSets / vm.itemsPerPage);
          vm.loadingDataSets = false;
          vm.dataSetsError = false;
          vm.areDataSetsTextSearched = true;
        }, function (error) {
          $log.error(error);
          vm.dataSetsError = true;
          vm.loadingDataSets = false;
        });
      }
    }

    // helper function to deal with search vs perms filtering
    function isFiltersEmpty () {
      if (vm.groupFilter.selectedName !== 'All' ||
        vm.groupFilter.public || vm.groupFilter.owned) {
        return false;
      }
      return true;
    }
   /*
   * ---------------------------------------------------------
   * Watchers
   * ---------------------------------------------------------
   */
    vm.$onInit = function () {
      if (!vm.isLoggedIn) {
        vm.params.public = true;
        vm.refreshDataSets();
      }

      $scope.$watchCollection(
        function () {
          return vm.dashboardParentCtrl.groups;
        },
        function () {
          vm.groups = vm.dashboardParentCtrl.groups;
        }
      );

      $scope.$watchCollection(
        function () {
          return primaryGroupService.primaryGroup;
        },
        function () {
          vm.primaryGroupID = primaryGroupService.primaryGroup.id;
        }
      );
    };
  }
})();
