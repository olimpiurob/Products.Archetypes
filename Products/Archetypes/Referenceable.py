from zope.component import getUtility
from zope.component import queryUtility
from zope.interface import implements

from Products.Archetypes import config
from Products.Archetypes.exceptions import ReferenceException
from Products.Archetypes.interfaces import IReferenceCatalog
from Products.Archetypes.interfaces import IReferenceable
from Products.Archetypes.interfaces import IUIDCatalog
from Products.Archetypes.interfaces.referenceable import IReferenceable as DEPRECATED
from Products.Archetypes.utils import shasattr

from Acquisition import aq_base, aq_parent, aq_inner
from OFS.ObjectManager import BeforeDeleteException

from Products.CMFCore.permissions import View
from OFS.CopySupport import CopySource
from OFS.Folder import Folder
from utils import getRelURL

from Globals import InitializeClass
from AccessControl import ClassSecurityInfo

####
## In the case of:
## - a copy:
##   * we want to lose refs on the new object
##   * we want to keep refs on the orig object
## - a cut/paste
##   * we want to keep refs
## - a delete:
##   * to lose refs
####

#include graph supporting methods
from ref_graph import get_cmapx, get_png

class Referenceable(CopySource):
    """ A Mix-in for Referenceable objects """
    isReferenceable = 1
    implements(IReferenceable)
    __implements__ = (DEPRECATED,)

    security = ClassSecurityInfo()
    # XXX FIXME more security

    def reference_url(self):
        """like absoluteURL, but return a link to the object with this UID"""
        tool = getUtility(IReferenceCatalog)
        return tool.reference_url(self)

    def hasRelationshipTo(self, target, relationship=None):
        tool = getUtility(IReferenceCatalog)
        return tool.hasRelationshipTo(self, target, relationship)

    def addReference(self, object, relationship=None, referenceClass=None,
                     updateReferences=True, **kwargs):
        tool = getUtility(IReferenceCatalog)
        return tool.addReference(self, object, relationship, referenceClass,
                                 updateReferences, **kwargs)

    def deleteReference(self, target, relationship=None):
        tool = getUtility(IReferenceCatalog)
        return tool.deleteReference(self, target, relationship)

    def deleteReferences(self, relationship=None):
        tool = getUtility(IReferenceCatalog)
        return tool.deleteReferences(self, relationship)

    def getRelationships(self):
        """What kinds of relationships does this object have"""
        tool = getUtility(IReferenceCatalog)
        return tool.getRelationships(self)

    def getBRelationships(self):
        """
        What kinds of relationships does this object have from others
        """
        tool = getUtility(IReferenceCatalog)
        return tool.getBackRelationships(self)

    def getRefs(self, relationship=None, targetObject=None):
        """get all the referenced objects for this object"""
        tool = queryUtility(IReferenceCatalog)
        if tool is not None:
            refs = tool.getReferences(self, relationship, targetObject=targetObject)
            if refs:
                return [ref.getTargetObject() for ref in refs]
        return []

    def _getURL(self):
        """the url used as the relative path based uid in the catalogs"""
        return getRelURL(self, self.getPhysicalPath())

    def getBRefs(self, relationship=None, targetObject=None):
        """get all the back referenced objects for this object"""
        tool = getUtility(IReferenceCatalog)
        refs = tool.getBackReferences(self, relationship, targetObject=targetObject)
        if refs:
            return [ref.getSourceObject() for ref in refs]
        return []

    #aliases
    getReferences=getRefs
    getBackReferences=getBRefs

    def getReferenceImpl(self, relationship=None, targetObject=None):
        """get all the reference objects for this object    """
        tool = getUtility(IReferenceCatalog)
        refs = tool.getReferences(self, relationship, targetObject=targetObject)
        if refs:
            return refs
        return []

    def getBackReferenceImpl(self, relationship=None, targetObject=None):
        """get all the back reference objects for this object"""
        tool = getUtility(IReferenceCatalog)
        refs = tool.getBackReferences(self, relationship, targetObject=targetObject)
        if refs:
            return refs
        return []

    def _register(self, reference_manager=None):
        """register with the archetype tool for a unique id"""
        if self.UID() is not None:
            return

        if reference_manager is None:
            reference_manager = queryUtility(IReferenceCatalog)
        if reference_manager is not None:
            reference_manager.registerObject(self)

    def _unregister(self):
        """unregister with the archetype tool, remove all references"""
        reference_manager = getUtility(IReferenceCatalog)
        reference_manager.unregisterObject(self)

    def _getReferenceAnnotations(self):
        """given an object extract the bag of references for which it
        is the source"""
        if not getattr(aq_base(self), config.REFERENCE_ANNOTATION, None):
            setattr(self, config.REFERENCE_ANNOTATION,
                    Folder(config.REFERENCE_ANNOTATION))

        return getattr(self, config.REFERENCE_ANNOTATION).__of__(self)

    def _delReferenceAnnotations(self):
        """Removes annotation from self
        """
        if getattr(aq_base(self), config.REFERENCE_ANNOTATION, None):
            delattr(self, config.REFERENCE_ANNOTATION)

    def UID(self):
        return getattr(self, config.UUID_ATTR, None)

    def _setUID(self, uid):
        old_uid = self.UID()
        if old_uid is None:
            # Nothing to be done.
            return
        # Update forward references
        fw_refs = self.getReferenceImpl()
        for ref in fw_refs:
            assert ref.sourceUID == old_uid
            ref.sourceUID = uid
            item = ref
            container = aq_parent(aq_inner(ref))
            # We call manage_afterAdd to inform the
            # reference catalog about changes.
            ref.manage_afterAdd(item, container)
        # Update back references
        back_refs = self.getBackReferenceImpl()
        for ref in back_refs:
            assert ref.targetUID == old_uid
            ref.targetUID = uid
            item = ref
            container = aq_parent(aq_inner(ref))
            # We call manage_afterAdd to inform the
            # reference catalog about changes.
            ref.manage_afterAdd(item, container)
        setattr(self, config.UUID_ATTR, uid)
        item = self
        container = aq_parent(aq_inner(item))
        # We call manage_afterAdd to inform the
        # reference catalog about changes.
        self.manage_afterAdd(item, container)

    def _updateCatalog(self, container):
        """Update catalog after copy, rename ...
        """
        # the UID index needs to be updated for any annotations we
        # carry
        uc = queryUtility(IUIDCatalog)
        rc = queryUtility(IReferenceCatalog)

        if uc is not None:
            self._catalogUID(container, uc=uc)
            if rc is not None:
                self._catalogRefs(container, uc=uc, rc=rc)

    ## OFS Hooks
    def manage_afterAdd(self, item, container):
        """
        Get a UID
        (Called when the object is created or moved.)
        """
        isCopy = getattr(item, '_v_is_cp', None)
        if isCopy:
            # If the object is a copy of a existing object we
            # want to renew the UID, and drop all existing references
            # on the newly-created copy.
            setattr(self, config.UUID_ATTR, None)
            self._delReferenceAnnotations()

        ct = queryUtility(IReferenceCatalog)
        self._register(reference_manager=ct)
        self._updateCatalog(container)
        self._referenceApply('manage_afterAdd', item, container)

    def manage_afterClone(self, item):
        """
        Get a new UID (effectivly dropping reference)
        (Called when the object is cloned.)
        """
        uc = getUtility(IUIDCatalog)

        isCopy = getattr(item, '_v_is_cp', None)
        if isCopy:
            # if isCopy is True, manage_afterAdd should have assigned a
            # UID already.  Don't mess with UID anymore.
            return

        # TODO Should we ever get here after the isCopy flag addition??
        # If the object has no UID or the UID already exists, then
        # we should get a new one
        if (not shasattr(self,config.UUID_ATTR) or
            len(uc(UID=self.UID()))):
            setattr(self, config.UUID_ATTR, None)

        self._register()
        self._updateCatalog(self)

    def manage_beforeDelete(self, item, container):
        """
        Remove self from the catalog.
        (Called when the object is deleted or moved.)
        """

        # Change this to be "item", this is the root of this recursive
        # chain and it will be flagged in the correct mode
        storeRefs = getattr(item, '_v_cp_refs', None)
        if storeRefs is None:
            # The object is really going away, we want to remove
            # its references
            rc = getUtility(IReferenceCatalog)
            references = rc.getReferences(self)
            back_references = rc.getBackReferences(self)
            try:
                #First check the 'delete cascade' case
                if references:
                    for ref in references:
                        ref.beforeSourceDeleteInformTarget()
                #Then check the 'holding/ref count' case
                if back_references:
                    for ref in back_references:
                        ref.beforeTargetDeleteInformSource()
                # If nothing prevented it, remove all the refs
                self.deleteReferences()
            except ReferenceException, E:
                raise BeforeDeleteException(E)

        self._referenceApply('manage_beforeDelete', item, container)

        # Track the UUID
        # The object has either gone away, moved or is being
        # renamed, we still need to remove all UID/child refs
        self._uncatalogUID(container)
        self._uncatalogRefs(container)



    ## Catalog Helper methods
    def _catalogUID(self, aq, uc=None):
        if not uc:
            uc = getUtility(IUIDCatalog)
        url = self._getURL()
        uc.catalog_object(self, url)

    def _uncatalogUID(self, aq, uc=None):
        if uc is None:
            uc = queryUtility(IUIDCatalog)
        if uc is not None:
            url = self._getURL()
            # XXX This is an ugly workaround. This method shouldn't be called
            # twice for an object in the first place, so we don't have to check
            # if it is still cataloged. 
            rid = uc.getrid(url)
            if rid is not None:
                uc.uncatalog_object(url)

    def _catalogRefs(self, aq, uc=None, rc=None):
        annotations = self._getReferenceAnnotations()
        if annotations:
            if uc is None:
                uc = queryUtility(IUIDCatalog)
            if rc is None:
                rc = queryUtility(IReferenceCatalog)
            if uc is not None and rc is not None:
                for ref in annotations.objectValues():
                    url = getRelURL(uc, ref.getPhysicalPath())
                    uc.catalog_object(ref, url)
                    rc.catalog_object(ref, url)
                    ref._catalogRefs(uc, uc, rc)

    def _uncatalogRefs(self, aq, uc=None, rc=None):
        annotations = self._getReferenceAnnotations()
        if annotations:
            if uc is None:
                uc = queryUtility(IUIDCatalog)
            if rc is None:
                rc = queryUtility(IReferenceCatalog)
            if uc is not None and rc is not None:
                for ref in annotations.objectValues():
                    url = getRelURL(uc, ref.getPhysicalPath())
                    # XXX This is an ugly workaround. This method shouldn't be
                    # called twice for an object in the first place, so we don't
                    # have to check if it is still cataloged. 
                    uc_rid = uc.getrid(url)
                    if uc_rid is not None:
                        uc.uncatalog_object(url)
                    rc_rid = rc.getrid(url)
                    if rc_rid is not None:
                        rc.uncatalog_object(url)

    def _getCopy(self, container):
        # We only set the '_v_is_cp' flag here if it was already set.
        #
        # _getCopy gets called after _notifyOfCopyTo, which should set
        # _v_cp_refs appropriatedly.
        #
        # _getCopy is also called from WebDAV MOVE (though not from
        # 'manage_pasteObjects')
        is_cp_flag = getattr(self, '_v_is_cp', None)
        cp_refs_flag = getattr(self, '_v_cp_refs', None)
        ob = CopySource._getCopy(self, container)
        if is_cp_flag:
            setattr(ob, '_v_is_cp', is_cp_flag)
        if cp_refs_flag:
            setattr(ob, '_v_cp_refs', cp_refs_flag)
        return ob

    def _notifyOfCopyTo(self, container, op=0):
        """keep reference info internally when op == 1 (move)
        because in those cases we need to keep refs"""
        # This isn't really safe for concurrent usage, but the
        # worse case is not that bad and could be fixed with a reindex
        # on the archetype tool
        if op==1:
            self._v_cp_refs = 1
            self._v_is_cp = 0
        if op==0:
            self._v_cp_refs = 0
            self._v_is_cp = 1

    # Recursion Mgmt
    def _referenceApply(self, methodName, *args, **kwargs):
        # We always apply commands to our reference children
        # and if we are folderish we need to get those too
        # where as references are concerned
        children = []
        if shasattr(self, 'objectValues'):
            # Only apply to objects that subclass
            # from Referenceable, and only apply the
            # method from Referenceable. Otherwise manage_* will get
            # called multiple times.
            nc = lambda obj: isinstance(obj, Referenceable)
            children.extend(filter(nc, self.objectValues()))
        children.extend(self._getReferenceAnnotations().objectValues())
        if children:
            for child in children:
                if shasattr(Referenceable, methodName):
                    method = getattr(Referenceable, methodName)
                    method(*((child,) + args), **kwargs)

    # graph hooks
    security.declareProtected(View, 'getReferenceMap')
    def getReferenceMap(self):
        """The client side map for this objects references"""
        return get_cmapx(self)

    security.declareProtected(View, 'getReferencePng')
    def getReferencePng(self, REQUEST=None):
        """A png of the references for this object"""
        if REQUEST:
            REQUEST.RESPONSE.setHeader('content-type', 'image/png')
        return get_png(self)

InitializeClass(Referenceable)
