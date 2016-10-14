'use strict';

function MemberEditorCtrl (
  $timeout,
  $uibModalInstance,
  groupDataService,
  groupMemberService,
  member
) {
  this.$timeout = $timeout;
  this.$uibModalInstance = $uibModalInstance;
  this.groupDataService = groupDataService;
  this.groupMemberService = groupMemberService;
  this.member = member;
  this.alertType = 'info';
  this.responseMessage = '';

  this.close = function () {
    this.$uibModalInstance.dismiss();
  };
}

MemberEditorCtrl.prototype.promote = function () {
  var that = this;

  that.groupMemberService.add({
    uuid: that.groupDataService.activeGroup.manager_group_uuid,
    user_id: that.member.user_id
  }).$promise.then(
    function () {
      that.groupDataService.update();
      that.alertType = 'success';
      that.responseMessage = 'Successfully promoted member ' + that.member.username;
      that.$timeout(function () {
        that.$uibModalInstance.dismiss();
      }, 1500);
    }
  ).catch(function () {
    that.alertType = 'error';
    that.responseMessage = 'Error Could not promote member ' + that.member.username;
  });
};

MemberEditorCtrl.prototype.demote = function () {
  var that = this;

  that.groupMemberService.remove({
    uuid: that.groupDataService.activeGroup.manager_group_uuid,
    userId: that.member.user_id
  }).$promise.then(
    function () {
      that.groupDataService.update();
      that.alertType = 'success';
      that.responseMessage = 'Successfully demoted member ' + that.member.username;
      that.$timeout(function () {
        that.$uibModalInstance.dismiss();
      }, 1500);
    }
  ).catch(function () {
    that.alertType = 'error';
    that.responseMessage = 'Error, could not demote member ' +
      that.member.username + '. Last member and manager can not leave';
  });
};

MemberEditorCtrl.prototype.remove = function () {
  var that = this;

  that.groupMemberService.remove({
    uuid: that.groupDataService.activeGroup.uuid,
    userId: that.member.user_id
  }).$promise.then(
    function () {
      that.groupDataService.update();
      that.alertType = 'success';
      that.responseMessage = 'Successfully removed member' + that.member.username;
      that.$timeout(function () {
        that.$uibModalInstance.dismiss();
      }, 1500);
    }
  ).catch(function () {
    that.alertType = 'error';
    that.responseMessage = 'Error, could not remove member'
      + that.member.username + '. Last member and manager can not leave';
  });
};

angular
  .module('refineryCollaboration')
  .controller('MemberEditorCtrl', [
    '$timeout',
    '$uibModalInstance',
    'groupDataService',
    'groupMemberService',
    'member',
    MemberEditorCtrl
  ]);
