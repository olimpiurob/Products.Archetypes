"""
Unittests for a Schema Provider

$Id: test_schemaProvider.py,v 1.1.2.1 2004/03/30 23:38:33 bcsaller Exp $
"""

import os, sys
if __name__ == '__main__':
    execfile(os.path.join(sys.path[0], 'framework.py'))

from common import *
from utils import *

from Acquisition import aq_base
import Products.Archetypes.config as config
from Products.Archetypes.public import *
from Products.Archetypes.examples.DDocument import schema as DDocumentSchema
from Products.Archetypes.SchemaProvider import *

class SchemaProviderTests(ArcheSiteTestCase):
    def afterSetUp(self):
        ArcheSiteTestCase.afterSetUp(self)
        user = self.getManagerUser()
        newSecurityManager(None, user)
        self.init_collectors()

    def init_collectors(self):
        site = self.getPortal()
        at = site.archetype_tool
        at.registerSchemaCollector(SelfCollector())
        at.registerSchemaCollector(AcquisitionCollector())
        at.registerSchemaCollector(ReferenceCollector())
        
    def test_singleSchemaTest(self):
        # Test that the baseline get Schema Continues to Function
        # When no schema collector is associated with the object
        # (and hence no providers)
        site = self.getPortal()
        obja = makeContent(site, "DDocument", "obja")
        objb = makeContent(site, "SimpleType", "objb")
        
        assert obja.Schema() == DDocumentSchema
        assert objb.Schema() != DDocumentSchema

    def test_aqCollector(self):
        site = self.getPortal()
        at = site.archetype_tool
        
        folder = makeContent(site, "SimpleFolder", "folder")
        objb = makeContent(folder, "DDocument", "objb")

        #Lets say that folder is a schema provider for objB
        # (but in this case provides nothing)
        objb.setSchemaCollector('acquisition')
        assert objb.Schema() == DDocumentSchema

        # Now we need to make folder a provider of a new Schemata
        # and assert those fields appear on objb
        f = TextField('newField')
        testSchema = Schema ((f,))
        
        at.provideSchema(folder, testSchema)
        folder.setSchemaPriority(11) # low low pri
        g = objb.Schema()['newField']
        assert g.type == "text"
        assert g is f
        assert g is objb.Schema().fields()[-1]

    def testReferenceCollector(self):
        site = self.getPortal()
        at = site.archetype_tool
        
        folder = makeContent(site, "SimpleFolder", "folder")
        obja = makeContent(folder, "DDocument", "obja")
        objb = makeContent(folder, "DDocument", "objb")

        objb.setSchemaCollector('reference')

        a = TextField('FieldA')
        b = TextField('FieldB')
        testSchemaA = Schema ((a,))
        testSchemaB = Schema ((b,))

        folder.setSchemaPriority(11) # low low pri
        obja.setSchemaPriority(12) # and lower still pri


        
        objb.addReference(folder, relationship='schema_provider')
        objb.addReference(obja, relationship='schema_provider')
        
        at.provideSchema(folder, testSchemaA)
        at.provideSchema(obja, testSchemaB)

        schema = objb.Schema()
        assert schema.fields()[-2] is a
        assert schema.fields()[-1] is b
        
        
        
        
        

if __name__ == '__main__':
    framework()
else:
    # While framework.py provides its own test_suite()
    # method the testrunner utility does not.
    import unittest
    def test_suite():
        suite = unittest.TestSuite()
        suite.addTest(unittest.makeSuite(SchemaProviderTests))
        return suite
